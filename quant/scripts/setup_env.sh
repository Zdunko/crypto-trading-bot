#!/usr/bin/env bash
# Reproducible project environment (Claude Code Cloud, GitHub Actions, any Linux).
# Uses the exact dependency pins of the vendored Freqtrade release.
set -euo pipefail
cd "$(dirname "$0")/../.."

PYTHON_VERSION="${PYTHON_VERSION:-3.13}"
command -v uv >/dev/null || { echo "uv is required: https://docs.astral.sh/uv/" >&2; exit 1; }

[ -d .venv ] || uv venv .venv --python "$PYTHON_VERSION"
# shellcheck disable=SC1091
source .venv/bin/activate
uv pip install -r quant/requirements.txt
uv pip install -e .
freqtrade --version
