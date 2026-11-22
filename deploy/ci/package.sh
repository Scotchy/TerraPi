#!/usr/bin/env bash
set -euo pipefail
out=$1
mkdir -p "$out"
out=$(cd "$out" && pwd)
cd backend
tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner \
    -czf "$out/controller.tgz" run.py requirements-pi.txt terrapi/*.py
