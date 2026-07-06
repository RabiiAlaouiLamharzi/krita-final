#!/bin/bash
# One-shot setup: install plugin + video into Krita. No manual steps.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
exec "$ROOT/install-mac.sh"
