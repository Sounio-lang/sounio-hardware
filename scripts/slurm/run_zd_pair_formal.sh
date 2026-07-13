#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EISA_H_GATE_ID=formal exec "$ROOT/scripts/slurm/run_zd_pair_synth.sh" "$@"
