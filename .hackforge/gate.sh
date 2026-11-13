#!/usr/bin/env bash
# Signer gate: exit 0 only if everything passes. Grows with every milestone; never weaken it.
# Always-on checks + every DoD command of each contract in .hackforge/contracts/ whose status is "done".
# iOS checks need macOS + Xcode >= 26.4. On a machine without Xcode set SIGNER_GATE_SKIP_IOS=1 (printed as SKIP; the lead's Mac runs them).
set -euo pipefail
cd "$(dirname "$0")/.."

PY=""
for c in "core/.venv/bin/python" "core/.venv/Scripts/python.exe" "py -3" python3 python; do
  v=$($c -c 'import sys;print(sys.version_info[0])' 2>/dev/null | tr -d '\r' || true)
  [ "$v" = 3 ] && PY="$c" && break
done
[ -n "$PY" ] || { echo "no Python 3"; exit 1; }
python() { $PY "$@"; }
export PYTHONPATH="core${PYTHONPATH:+:$PYTHONPATH}"

fail=0
run() { # run <label> <command>
  echo "--- $1"
  if bash_out=$(eval "$2" 2>&1); then echo "PASS $1"; else echo "$bash_out" | tail -n 20; echo "FAIL $1"; fail=1; fi
}

# 1. Contracts are valid and tasks never share owned paths inside a milestone
run "contracts valid" "python - <<'EOF'
import json, glob, itertools, sys
bad = []
for f in sorted(glob.glob('.hackforge/contracts/M*.json')):
    c = json.load(open(f))
    ids = [t['id'] for t in c['tasks']]
    if len(ids) != len(set(ids)): bad.append(f + ': duplicate task id')
    for d in c['dod']:
        if not d.get('command'): bad.append(f + ': DoD without command ' + d['id'])
    def base(p): return p[:-3] if p.endswith('/**') else p
    for a, b in itertools.combinations(c['tasks'], 2):
        for pa in a['owned']:
            for pb in b['owned']:
                x, y = base(pa), base(pb)
                if x == y or x.startswith(y + '/') or y.startswith(x + '/'):
                    bad.append(f'{f}: {a[\"id\"]} and {b[\"id\"]} both own {pa} / {pb}')
print('\n'.join(bad)); sys.exit(1 if bad else 0)
EOF"

# 2. Frozen shared contract code and mock events
run "shared contracts" "python - <<'EOF'
import json, sys
sys.path.insert(0, 'core')
from signer_core import contracts as c
assert c.N_POINTS == 75 and len(c.POSE) + len(c.LEFT_HAND) + len(c.RIGHT_HAND) == 75
assert c.tier_for(0.85) == 'confirmed' and c.tier_for(0.6) == 'unsure' and c.tier_for(0.2) == 'none'
h = {'seq': 1, 'ts_ms': 1, 'w': 504, 'h': 896, 'source': 'mock', 'rot': 0}
assert c.unpack_frame(c.pack_frame(h, b'jpg')) == (h, b'jpg')
types = {json.loads(l)['type'] for l in open('contracts/events.example.jsonl') if l.strip()}
assert {'state', 'caption', 'retract', 'reply', 'stats', 'partial'} <= types, types
EOF"

# 3. Milestone DoD commands (status done)
while IFS=$'\t' read -r label cmd; do
  [ -n "$label" ] || continue
  cmd=${cmd%$'\r'}
  if [ "${SIGNER_GATE_SKIP_IOS:-0}" = 1 ] && [[ "$cmd" == xcodebuild* ]]; then echo "SKIP $label (SIGNER_GATE_SKIP_IOS=1)"; continue; fi
  run "$label" "$cmd"
done < <(python - <<'EOF'
import json, glob
for f in sorted(glob.glob('.hackforge/contracts/M*.json')):
    c = json.load(open(f))
    if c.get('status') != 'done':
        continue
    for d in c['dod']:
        print(f"{c['milestone']}.{d['id']} {d['check'][:60]}\t{d['command']}")
EOF
)

if [ "$fail" = 0 ]; then echo "GATE PASS"; else echo "GATE FAIL"; fi
exit "$fail"
