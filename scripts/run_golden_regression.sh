#!/usr/bin/env bash
# Run golden-set regression tests (deterministic stub graph). Safe for CI and class demos.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
exec pytest tests/golden/test_golden_regression.py -v --tb=short "$@"
