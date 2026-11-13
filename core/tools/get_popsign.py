#!/usr/bin/env python3
"""Fetch only the vocabulary signs of PopSign ASL v1.0 (CC BY 4.0) from data/VOCAB.md.

PopSign layout (found in M0.4, see data/popsign/README.md):
  https://signdata.cc.gatech.edu/data/popsign_v1_0/{game,non-game}/{train,val,test}/<sign>.tar
One uncompressed tar per (sign, split), anonymous, HTTP Range supported. Members are
  <sign>/<participant>-<sign>-<YYYY_MM_DD_HH_MM_SS.mmm>-<take>.mp4   (~4-6 MB, 1944x2592 phone video)
We only use `game` (the clip shows exactly the target sign). Because tars are plain, the manifest records each
member's byte offset and size, so a clip is one Range request and the multi-GB tars are never downloaded whole.

Modes
  --refresh-manifest   network: walk the tar headers (512-byte Range reads) and write data/popsign/manifest.json
  --dry-run            offline: read VOCAB.md + manifest.json only, print the plan, exit 1 on any gap
  (default)            network: download the planned clips into data/popsign/raw/<popsign_name>/ (gitignored)
  --selftest           offline checks of the parsers, the walker and the planner

Stdlib only. Run `python core/tools/get_popsign.py --help`.
"""
from __future__ import annotations

import argparse
import datetime as dt
import http.client
import json
import re
import sys
import tarfile
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # core/ -> `import signer_core`
from signer_core.contracts import REST  # noqa: E402  (stdlib-only module)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_VOCAB = ROOT / "data" / "VOCAB.md"
DEFAULT_MANIFEST = ROOT / "data" / "popsign" / "manifest.json"
DEFAULT_OUT = ROOT / "data" / "popsign" / "raw"

HOST = "signdata.cc.gatech.edu"
DATASET = "popsign_v1_0"
VARIANT = "game"  # PopSign's "non-game" bucket holds alternate signs; never used
SPLITS = ("train", "val", "test")
SCHEMA = "popsign-manifest.v1"
BLOCK = 512

VOCAB_ROW = re.compile(r"^\| ([A-Z][A-Z0-9_-]*) \|(.*)\| (popsign|own) \|(.*)\|\s*$")
SIGN_NAME = re.compile(r"^[a-z0-9]+$")


# ----------------------------------------------------------------------------- vocabulary

def parse_vocab(path: Path) -> list[dict]:
    """Rows of data/VOCAB.md: {gloss, english, source, popsign_name}."""
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not VOCAB_ROW.match(line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 4:
            raise ValueError(f"VOCAB row needs 4 cells: {line!r}")
        gloss, english, source, popsign_name = cells
        rows.append({"gloss": gloss, "english": english, "source": source, "popsign_name": popsign_name})
    glosses = [r["gloss"] for r in rows]
    if len(set(glosses)) != len(glosses):
        raise ValueError("VOCAB.md has duplicate GLOSS values")
    for r in rows:
        if r["source"] == "popsign" and not SIGN_NAME.match(r["popsign_name"]):
            raise ValueError(f"{r['gloss']}: popsign row needs a PopSign sign name, got {r['popsign_name']!r}")
        if r["source"] == "own" and r["popsign_name"] != "-":
            raise ValueError(f"{r['gloss']}: own row must have popsign_name '-'")
        if r["gloss"] == REST and r["source"] != "own":
            raise ValueError("REST must be an own row")
    return rows


def popsign_rows(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r["source"] == "popsign"]


# ----------------------------------------------------------------------------- urls and names

def tar_path(sign: str, split: str) -> str:
    return f"/data/{DATASET}/{VARIANT}/{split}/{sign}.tar"


def tar_url(sign: str, split: str) -> str:
    return f"https://{HOST}{tar_path(sign, split)}"


def page_url(sign: str) -> str:
    return f"https://{HOST}/view/datasets/{DATASET}/{VARIANT}/{sign}/index.html"


def signer_of(member: str, sign: str) -> str:
    """'<sign>/4a.8018-<sign>-2023_01_11_14_40_31.356-0.mp4' -> '8018' (numeric participant id)."""
    base = member.rsplit("/", 1)[-1]
    m = re.match(rf"^(.*?)-{re.escape(sign)}-\d{{4}}_", base)
    if not m:
        return "unknown"
    digits = re.search(r"(\d+)$", m.group(1))
    return digits.group(1) if digits else m.group(1)


# ----------------------------------------------------------------------------- tar walking (Range)

def _pax_path(payload: bytes) -> tuple[str | None, int | None]:
    path = size = None
    for rec in payload.split(b"\n"):
        if b" " not in rec:
            continue
        kv = rec.split(b" ", 1)[1]
        if kv.startswith(b"path="):
            path = kv[5:].decode("utf-8", "surrogateescape")
        elif kv.startswith(b"size="):
            size = int(kv[5:])
    return path, size


def walk_tar(fetch, total: int) -> list[dict]:
    """List regular members of an uncompressed tar via header reads only.

    fetch(start, end_inclusive) -> bytes. Returns [{member, offset, bytes}] where offset is the byte offset of the
    member's data inside the tar.
    """
    members = []
    pos = 0
    pending_name = None
    pending_size = None
    while pos + BLOCK <= total:
        hdr = fetch(pos, pos + BLOCK - 1)
        if len(hdr) < BLOCK or hdr == b"\0" * BLOCK:
            break
        try:
            info = tarfile.TarInfo.frombuf(hdr, "utf-8", "surrogateescape")
        except tarfile.TarError as e:
            raise RuntimeError(f"bad tar header at byte {pos}: {e}") from e
        data_off = pos + BLOCK
        padded = ((info.size + BLOCK - 1) // BLOCK) * BLOCK
        if info.type in (tarfile.GNUTYPE_LONGNAME, tarfile.XHDTYPE):
            payload = fetch(data_off, data_off + info.size - 1)
            if info.type == tarfile.GNUTYPE_LONGNAME:
                pending_name = payload.rstrip(b"\0").decode("utf-8", "surrogateescape")
            else:
                pending_name, pending_size = _pax_path(payload)
        elif info.type in (tarfile.REGTYPE, tarfile.AREGTYPE):
            size = pending_size if pending_size is not None else info.size
            members.append({"member": pending_name or info.name, "offset": data_off, "bytes": size})
            padded = ((size + BLOCK - 1) // BLOCK) * BLOCK
            pending_name = pending_size = None
        else:  # directories, global pax headers, ...
            pending_name = pending_size = None
        pos = data_off + padded
    return members


# ----------------------------------------------------------------------------- http helpers

class Http:
    """One keep-alive HTTPS connection with Range support and retries. Not shared between threads."""

    def __init__(self, host: str = HOST, timeout: float = 60.0):
        self.host, self.timeout, self.conn = host, timeout, None

    def _connect(self):
        self.close()
        self.conn = http.client.HTTPSConnection(self.host, timeout=self.timeout)

    def close(self):
        if self.conn is not None:
            try:
                self.conn.close()
            finally:
                self.conn = None

    def range(self, path: str, start: int, end: int, retries: int = 6) -> tuple[bytes, int | None]:
        """GET bytes start..end (inclusive). Returns (body, total_size_from_Content-Range)."""
        last = None
        for attempt in range(retries):
            try:
                if self.conn is None:
                    self._connect()
                self.conn.request("GET", path, headers={"Range": f"bytes={start}-{end}", "User-Agent": "signer-hackathon/0.1"})
                resp = self.conn.getresponse()
                body = resp.read()
                if resp.status != 206:
                    raise RuntimeError(f"HTTP {resp.status} for Range {start}-{end} of {path} (expected 206)")
                m = re.match(r"bytes (\d+)-(\d+)/(\d+)", resp.getheader("Content-Range", ""))
                if not m or int(m.group(1)) != start:
                    raise RuntimeError(f"unexpected Content-Range for {path}: {resp.getheader('Content-Range')}")
                return body, int(m.group(3))
            except (OSError, http.client.HTTPException, RuntimeError) as e:
                last = e
                self.close()
                if isinstance(e, RuntimeError) and "HTTP 4" in str(e):
                    break
                time.sleep(min(2 ** attempt, 20))
        raise RuntimeError(f"giving up on {path} {start}-{end}: {last}")


# ----------------------------------------------------------------------------- manifest refresh

def _walk_one(sign: str, split: str) -> tuple[str, str, int, list[dict]]:
    http_ = Http()
    path = tar_path(sign, split)
    try:
        _, total = http_.range(path, 0, BLOCK - 1)

        def fetch(a, b):
            return http_.range(path, a, b)[0]

        members = walk_tar(fetch, total)
    finally:
        http_.close()
    return sign, split, total, members


def refresh_manifest(rows: list[dict], manifest_path: Path, workers: int) -> int:
    signs = sorted({r["popsign_name"]: r["gloss"] for r in popsign_rows(rows)}.items())
    jobs = [(s, sp) for s, _ in signs for sp in SPLITS]
    print(f"walking {len(jobs)} tars ({len(signs)} signs x {len(SPLITS)} splits) with {workers} workers ...", flush=True)
    results: dict[tuple[str, str], tuple[int, list[dict]]] = {}
    errors = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_walk_one, s, sp): (s, sp) for s, sp in jobs}
        for n, fut in enumerate(as_completed(futs), 1):
            s, sp = futs[fut]
            try:
                _, _, total, members = fut.result()
                results[(s, sp)] = (total, members)
                print(f"[{n}/{len(jobs)}] {s}/{sp}: {len(members)} clips, {total / 1e6:.0f} MB tar "
                      f"({time.time() - t0:.0f}s)", flush=True)
            except Exception as e:  # noqa: BLE001
                errors.append((s, sp, str(e)))
                print(f"[{n}/{len(jobs)}] {s}/{sp}: FAILED {e}", file=sys.stderr, flush=True)
    if errors:
        print(f"{len(errors)} tar walks failed; manifest not written", file=sys.stderr)
        return 1

    fetched = dt.date.today().isoformat()
    out = {
        "schema": SCHEMA,
        "dataset": DATASET,
        "variant": VARIANT,
        "license": "CC BY 4.0 (PopSign ASL v1.0, Georgia Tech / DPAN)",
        "host": f"https://{HOST}",
        "fetched": fetched,
        "signs": {},
    }
    for s, gloss in signs:
        clips, tars = [], {}
        for sp in SPLITS:
            total, members = results[(s, sp)]
            tars[sp] = {"url": tar_url(s, sp), "bytes": total}
            for m in members:
                clips.append({"member": m["member"], "split": sp, "signer": signer_of(m["member"], s),
                              "offset": m["offset"], "bytes": m["bytes"]})
        clips.sort(key=lambda c: (c["split"], c["member"]))
        out["signs"][s] = {"gloss": gloss, "popsign_name": s, "source_url": page_url(s), "tars": tars,
                           "fetched": fetched, "clips": clips}
    write_manifest(manifest_path, out)
    print(f"wrote {manifest_path} ({manifest_path.stat().st_size / 1e6:.2f} MB)")
    return 0


def write_manifest(path: Path, data: dict) -> None:
    """One clip per line so diffs stay readable."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["{"]
    head = {k: v for k, v in data.items() if k != "signs"}
    for k, v in head.items():
        lines.append(f"  {json.dumps(k)}: {json.dumps(v)},")
    lines.append('  "signs": {')
    names = list(data["signs"])
    for i, name in enumerate(names):
        e = data["signs"][name]
        meta = {k: v for k, v in e.items() if k != "clips"}
        lines.append(f"    {json.dumps(name)}: {{")
        for k, v in meta.items():
            lines.append(f"      {json.dumps(k)}: {json.dumps(v)},")
        lines.append('      "clips": [')
        clips = e["clips"]
        for j, c in enumerate(clips):
            lines.append("        " + json.dumps(c, separators=(",", ":")) + ("," if j < len(clips) - 1 else ""))
        lines.append("      ]")
        lines.append("    }" + ("," if i < len(names) - 1 else ""))
    lines.append("  }")
    lines.append("}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ----------------------------------------------------------------------------- planning

def pick_clips(clips: list[dict], n: int) -> list[dict]:
    """First n clips, taken round-robin across signer ids (deterministic: signers and clips sorted)."""
    by_signer: dict[str, list[dict]] = {}
    for c in sorted(clips, key=lambda c: (c["member"], c["split"])):
        by_signer.setdefault(c["signer"], []).append(c)
    signers = sorted(by_signer)
    picked = []
    rnd = 0
    while len(picked) < n and any(rnd < len(v) for v in by_signer.values()):
        for s in signers:
            if rnd < len(by_signer[s]) and len(picked) < n:
                picked.append(by_signer[s][rnd])
        rnd += 1
    return picked


def build_plan(rows: list[dict], manifest: dict, per_sign: int, signs: set[str] | None):
    """Returns (plan, problems). plan = [{gloss, sign, clip, url}] sorted; problems = list of strings."""
    problems, plan = [], []
    entries = manifest.get("signs", {})
    vocab_names = {r["popsign_name"] for r in popsign_rows(rows)}
    for r in popsign_rows(rows):
        if signs and r["gloss"] not in signs and r["popsign_name"] not in signs:
            continue
        e = entries.get(r["popsign_name"])
        if not e or not e.get("clips"):
            problems.append(f"{r['gloss']}: no manifest entry for popsign_name '{r['popsign_name']}' "
                            f"(run --refresh-manifest)")
            continue
        for c in pick_clips(e["clips"], per_sign):
            url = e["tars"][c["split"]]["url"]
            if not (c["member"].startswith(r["popsign_name"] + "/") and url.endswith(f"/{r['popsign_name']}.tar")):
                problems.append(f"{r['gloss']}: clip {c['member']} / {url} is outside the vocabulary sign")
                continue
            plan.append({"gloss": r["gloss"], "sign": r["popsign_name"], "clip": c, "url": url})
    plan.sort(key=lambda p: (p["sign"], p["clip"]["member"]))
    extra = sorted(set(entries) - vocab_names)
    return plan, problems, extra


def shard_of(plan: list[dict], i: int, n: int) -> list[dict]:
    return [p for k, p in enumerate(plan) if k % n == i]


def parse_shard(text: str) -> tuple[int, int]:
    m = re.fullmatch(r"(\d+)/(\d+)", text)
    if not m or int(m.group(2)) < 1 or int(m.group(1)) >= int(m.group(2)):
        raise argparse.ArgumentTypeError("--shard must be i/n with 0 <= i < n, e.g. 0/3")
    return int(m.group(1)), int(m.group(2))


def print_plan(plan: list[dict]) -> None:
    by = {}
    for p in plan:
        d = by.setdefault((p["gloss"], p["sign"]), {"n": 0, "bytes": 0, "signers": set()})
        d["n"] += 1
        d["bytes"] += p["clip"]["bytes"]
        d["signers"].add(p["clip"]["signer"])
    print(f"{'gloss':<12}{'popsign':<12}{'files':>6}{'MB':>9}{'signers':>9}")
    for (g, s), d in sorted(by.items()):
        print(f"{g:<12}{s:<12}{d['n']:>6}{d['bytes'] / 1e6:>9.1f}{len(d['signers']):>9}")
    tot = sum(p["clip"]["bytes"] for p in plan)
    print(f"{'TOTAL':<24}{len(plan):>6}{tot / 1e6:>9.1f}   ({tot / 1e9:.2f} GB)")


# ----------------------------------------------------------------------------- download

def download_clip(http_: Http, item: dict, out_dir: Path) -> tuple[str, int]:
    """Download one member to raw/<sign>/<name>.mp4. Resumable. Returns (status, bytes_fetched)."""
    c = item["clip"]
    path = urllib.parse.urlsplit(item["url"]).path
    dest_dir = out_dir / item["sign"]
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / c["member"].rsplit("/", 1)[-1]
    if dest.exists() and dest.stat().st_size == c["bytes"]:
        return "skip", 0
    part = dest.with_name(dest.name + ".part")
    have = part.stat().st_size if part.exists() else 0
    if have > c["bytes"]:
        part.unlink()
        have = 0
    fetched = 0
    if have < c["bytes"]:
        start = c["offset"] + have
        end = c["offset"] + c["bytes"] - 1
        body, _ = http_.range(path, start, end)
        if len(body) != end - start + 1:
            raise RuntimeError(f"short read for {c['member']}: {len(body)} of {end - start + 1}")
        with open(part, "ab") as f:
            f.write(body)
        fetched = len(body)
    if part.stat().st_size != c["bytes"]:
        raise RuntimeError(f"{part} has {part.stat().st_size} bytes, expected {c['bytes']}")
    with open(part, "rb") as f:
        if f.read(12)[4:8] != b"ftyp":
            part.unlink()
            raise RuntimeError(f"{c['member']}: not an mp4 (offsets in the manifest may be stale)")
    part.replace(dest)
    return "ok", fetched


def run_download(plan: list[dict], out_dir: Path, workers: int) -> int:
    tls = threading.local()
    done = {"n": 0, "bytes": 0, "skipped": 0}
    lock = threading.Lock()
    failures = []

    def work(item):
        if not hasattr(tls, "http"):
            tls.http = Http()
        return item, download_clip(tls.http, item, out_dir)

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(work, it) for it in plan]
        for fut in as_completed(futs):
            try:
                item, (status, nbytes) = fut.result()
            except Exception as e:  # noqa: BLE001
                failures.append(str(e))
                print(f"FAILED {e}", file=sys.stderr, flush=True)
                continue
            with lock:
                done["n"] += 1
                done["bytes"] += nbytes
                done["skipped"] += status == "skip"
                if done["n"] % 10 == 0 or done["n"] == len(plan):
                    mb = done["bytes"] / 1e6
                    print(f"{done['n']}/{len(plan)} clips ({done['skipped']} already there), {mb:.0f} MB fetched, "
                          f"{mb / max(time.time() - t0, 1e-3):.1f} MB/s", flush=True)
    print(f"done: {done['n']} ok, {len(failures)} failed, {done['bytes'] / 1e6:.0f} MB fetched into {out_dir}")
    return 1 if failures else 0


# ----------------------------------------------------------------------------- selftest

def selftest() -> int:
    import io
    import socket
    import tempfile

    # tar walker on a synthetic tar with a dir, a long name and normal members
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.GNU_FORMAT) as tf:
        d = tarfile.TarInfo("hello")
        d.type = tarfile.DIRTYPE
        tf.addfile(d)
        for name, size in (("hello/4a.8018-hello-2023_01_11_14_40_31.356-0.mp4", 1000),
                           ("hello/" + "x" * 120 + ".mp4", 513),
                           ("hello/gtsignstudy4a.8031-hello-2023_01_24_20_27_17.907-1.mp4", 512)):
            ti = tarfile.TarInfo(name)
            ti.size = size
            tf.addfile(ti, io.BytesIO(b"\0\0\0\0ftypmp42" + b"a" * (size - 12)))
    raw = buf.getvalue()
    got = walk_tar(lambda a, b: raw[a:b + 1], len(raw))
    assert [g["bytes"] for g in got] == [1000, 513, 512], got
    for g in got:
        assert raw[g["offset"] + 4:g["offset"] + 8] == b"ftyp", g
    assert got[1]["member"].endswith("x" * 120 + ".mp4")
    assert signer_of(got[0]["member"], "hello") == "8018"
    assert signer_of(got[2]["member"], "hello") == "8031"

    # round-robin picking
    clips = [{"member": f"s/{sg}-s-{k}", "split": "train", "signer": sg, "offset": 0, "bytes": 1}
             for sg, cnt in (("1", 5), ("2", 1), ("3", 3)) for k in range(cnt)]
    first = pick_clips(clips, 6)
    assert [c["signer"] for c in first] == ["1", "2", "3", "1", "3", "1"], [c["signer"] for c in first]
    assert len(pick_clips(clips, 100)) == 9

    # vocab parser + dry-run planning with sockets disabled
    with tempfile.TemporaryDirectory() as td:
        v = Path(td) / "VOCAB.md"
        v.write_text("| GLOSS | english | source (popsign/own) | popsign_name |\n|---|---|---|---|\n"
                     "| HELLO | hello | popsign | hello |\n| HELP | help | own | - |\n| REST | (rest) | own | - |\n")
        rows = parse_vocab(v)
        assert [r["gloss"] for r in rows] == ["HELLO", "HELP", "REST"], rows
        m = Path(td) / "manifest.json"
        man = {"schema": SCHEMA, "signs": {"hello": {"gloss": "HELLO", "popsign_name": "hello", "source_url": "x",
               "tars": {sp: {"url": tar_url("hello", sp), "bytes": 1} for sp in SPLITS},
               "clips": [{"member": "hello/a", "split": "val", "signer": "1", "offset": 512, "bytes": 10}]}}}
        write_manifest(m, man)
        assert json.loads(m.read_text()) == man
        real_socket = socket.socket

        def no_net(*a, **k):
            raise AssertionError("network access attempted")
        socket.socket = no_net
        try:
            rc = main(["--vocab", str(v), "--manifest", str(m), "--dry-run"])
            assert rc == 0, rc
            m.write_text(json.dumps({"schema": SCHEMA, "signs": {}}))
            assert main(["--vocab", str(v), "--manifest", str(m), "--dry-run"]) == 1
        finally:
            socket.socket = real_socket
    print("selftest ok")
    return 0


# ----------------------------------------------------------------------------- main

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vocab", type=Path, default=DEFAULT_VOCAB, help="data/VOCAB.md (default: from repo root)")
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="download dir (gitignored)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--refresh-manifest", action="store_true", help="network: rebuild the manifest from the tar headers")
    mode.add_argument("--dry-run", action="store_true", help="offline: print the plan; exit 1 if the manifest has gaps")
    mode.add_argument("--selftest", action="store_true", help="offline self checks")
    ap.add_argument("--per-sign", type=int, default=100, help="clips per sign, round-robin across signers (default 100)")
    ap.add_argument("--signs", default="", help="comma list of GLOSS or popsign names to limit to")
    ap.add_argument("--shard", type=parse_shard, default=(0, 1), metavar="i/n", help="this machine's part, 0 <= i < n")
    ap.add_argument("--workers", type=int, default=None, help="parallel connections (default 12 refresh, 4 download)")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    if args.per_sign < 1:
        ap.error("--per-sign must be >= 1")
    rows = parse_vocab(args.vocab)
    signs = {s.strip() for s in args.signs.split(",") if s.strip()} or None
    if signs:
        known = {r["gloss"] for r in popsign_rows(rows)} | {r["popsign_name"] for r in popsign_rows(rows)}
        unknown = signs - known
        if unknown:
            print(f"unknown --signs {sorted(unknown)}; PopSign rows in {args.vocab.name}: "
                  f"{sorted(r['gloss'] for r in popsign_rows(rows))}", file=sys.stderr)
            return 2

    if args.refresh_manifest:
        if signs:
            rows = [r for r in rows if r["source"] != "popsign" or r["gloss"] in signs or r["popsign_name"] in signs]
        return refresh_manifest(rows, args.manifest, args.workers or 12)

    if not args.manifest.exists():
        print(f"{args.manifest} missing: run --refresh-manifest once (needs network)", file=sys.stderr)
        return 1
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    plan, problems, extra = build_plan(rows, manifest, args.per_sign, signs)
    i, n = args.shard
    plan = shard_of(plan, i, n)

    if args.dry_run:
        print(f"dry-run: {len(popsign_rows(rows))} popsign signs in {args.vocab.name}, manifest fetched "
              f"{manifest.get('fetched')}, --per-sign {args.per_sign}, shard {i}/{n}")
        print_plan(plan)
        if extra:
            print(f"note: manifest also has signs outside the vocabulary (never planned): {extra}")
        for p in problems:
            print(f"PROBLEM: {p}", file=sys.stderr)
        return 1 if problems else 0

    if problems:
        for p in problems:
            print(f"PROBLEM: {p}", file=sys.stderr)
        return 1
    print_plan(plan)
    return run_download(plan, args.out, args.workers or 4)


if __name__ == "__main__":
    sys.exit(main())
