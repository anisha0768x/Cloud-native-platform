"""Start the local platform independently of a terminal, then verify readiness."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import urlopen
import webbrowser

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT / 'CloudNativePlatform' if (ROOT / 'CloudNativePlatform' / 'run_local.py').exists() else ROOT
URL = 'http://127.0.0.1:8080'

def healthy():
    try:
        with urlopen(URL + '/health', timeout=2) as response:
            data = json.load(response)
            return data.get('status') == 'ok' and data.get('service') == 'api-gateway'
    except Exception:
        return False

def main():
    if not healthy():
        with socket.socket() as probe:
            if probe.connect_ex(('127.0.0.1', 8080)) == 0:
                raise RuntimeError('Port 8080 is occupied by an unresponsive or different application. No process was stopped.')
        python = PROJECT / '.venv' / 'Scripts' / 'python.exe'
        if not python.exists():
            raise RuntimeError('Create .venv and install requirements.txt in ' + str(PROJECT))
        log_dir = Path(os.environ.get('LOCALAPPDATA', str(ROOT))) / 'CloudNativePlatform' / 'logs'
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / 'server.log'
        with log_path.open('a', encoding='utf-8') as log:
            process = subprocess.Popen([str(python), 'run_local.py'], cwd=PROJECT,
                stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS)
        for _ in range(30):
            if healthy():
                break
            if process.poll() is not None:
                raise RuntimeError('Server stopped during startup. See ' + str(log_path))
            time.sleep(1)
        else:
            raise RuntimeError('Server did not become ready. See ' + str(log_path))
    print('Platform ready: ' + URL)
    if '--no-browser' not in sys.argv:
        webbrowser.open(URL)

if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('STARTUP ERROR: ' + str(error), file=sys.stderr)
        sys.exit(1)
