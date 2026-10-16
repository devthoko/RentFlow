#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "$0")" && pwd)"
exec bash "$root/install.sh" --upgrade --prefix "$root" "$@"
