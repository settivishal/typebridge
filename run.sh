#!/bin/sh
# One-command start: creates .venv, installs deps, runs the server. Extra args go to server.py.
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt
exec .venv/bin/python server.py "$@"
