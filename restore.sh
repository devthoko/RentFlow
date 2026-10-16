#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "$0")" && pwd)"
archive="$1"
shift
exec python3 "$root/scripts/manage.py" restore --prefix "$root" --archive "$archive" "$@"
