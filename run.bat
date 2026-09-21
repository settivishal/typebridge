@echo off
rem One-command start: creates .venv, installs deps, runs the server. Extra args go to server.py.
cd /d "%~dp0"
if not exist .venv py -3 -m venv .venv || python -m venv .venv
.venv\Scripts\pip install -q -r requirements.txt
.venv\Scripts\python server.py %*
