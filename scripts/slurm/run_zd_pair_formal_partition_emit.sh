#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export CPUS="${CPUS:-8}"
export MEMORY="${MEMORY:-64G}"
export TIME_LIMIT="${TIME_LIMIT:-00:45:00}"
EISA_H_GATE_ID=formal-partition-emit exec "$ROOT/scripts/slurm/run_zd_pair_synth.sh" "$@"
