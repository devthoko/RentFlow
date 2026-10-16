#!/usr/bin/env bash
set -euo pipefail
prefix="$1"
test -n "$prefix"
mkdir -p "$prefix/runtime/lib"
work="$(mktemp -d)"
trap 'rm -rf -- "$work"' EXIT
if [ ! -f "$prefix/runtime/lib/libsqlite3.so.0" ]; then
  curl --retry 3 --connect-timeout 30 -fsSL https://www.sqlite.org/2026/sqlite-autoconf-3540000.tar.gz -o "$work/sqlite.tar.gz"
  python3 - "$work/sqlite.tar.gz" <<'PY'
import hashlib,sys
assert hashlib.sha3_256(open(sys.argv[1],'rb').read()).hexdigest()=='f5e3e724e9c9b3b5d512c76b02082091a59eeea9becd169a9fbf4d376403acce','SQLite-Prüfsumme stimmt nicht'
PY
  tar -xzf "$work/sqlite.tar.gz" -C "$work"
  cc -O2 -fPIC -shared -DSQLITE_THREADSAFE=1 -DSQLITE_ENABLE_FTS5 -DSQLITE_ENABLE_RTREE -DSQLITE_ENABLE_COLUMN_METADATA -DSQLITE_ENABLE_MATH_FUNCTIONS "$work/sqlite-autoconf-3540000/sqlite3.c" -o "$work/libsqlite3.so.0" -lm -ldl -lpthread
  install -m 755 "$work/libsqlite3.so.0" "$prefix/runtime/lib/libsqlite3.so.0"
  ln -sfn libsqlite3.so.0 "$prefix/runtime/lib/libsqlite3.so"
fi
export LD_LIBRARY_PATH="$prefix/runtime/lib"
python3 -c "import sqlite3; assert sqlite3.sqlite_version_info >= (3,51,3); print('SQLite',sqlite3.sqlite_version)"
