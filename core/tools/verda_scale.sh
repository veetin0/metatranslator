#!/usr/bin/env bash
# Run ON the Verda box from the repo root: bigger ASL Citizen vocabulary + every clip per gloss, then eval + final train.
# Keeps the 600-gloss artefacts (VOCAB_LARGE.md, gru_large.pt) as *_600 backups. Log: scale.log
set -euo pipefail
cd "$(dirname "$0")/../.."
export PYTHONPATH=core
PY=core/.venv/bin/python
N=${N:-1500}
cp -n data/VOCAB_LARGE.md data/VOCAB_LARGE_600.md || true
cp -n data/models/gru_large.pt data/models/gru_large_600.pt || true
$PY core/tools/ac_counts.py /tmp/ac_counts.json
$PY core/tools/pick_vocab_large.py --n "$N" --min-clips 20 --counts /tmp/ac_counts.json
$PY core/tools/get_asl_citizen_large.py --workers 24 --max-per-gloss 1000
$PY core/tools/train_large.py --eval --out eval/results/m7_scale.json
$PY core/tools/train_large.py --final
echo DONE
