"""Stop only an identified, idle SpatialStage server; never kill by port."""
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time
from urllib.request import urlopen


def stop_engine(repo, port=8765):
    repo = Path(repo).resolve()
    def get(path):
        with urlopen(f'http://127.0.0.1:{port}/api/{path}', timeout=3) as response:
            return json.load(response)
    health = get('health')
    identity = health.get('runtime', {})
    pid = identity.get('pid')
    allowed = {(repo / 'SpatialStage-test-data').resolve(), Path('~/.spatialstage/projects').expanduser().resolve()}
    custom = os.environ.get('STAGE_SPATIAL_DATA')
    if custom:
        allowed.add(Path(custom).expanduser().resolve())
    if (type(pid) is not int or pid <= 1 or identity.get('source_root') != str(repo)
            or Path(identity.get('data_root', '')).resolve() not in allowed
            or not re.fullmatch(r'[a-f0-9]{64}', identity.get('source_sha256', ''))
            or 'simulation' not in health.get('features', [])):
        raise RuntimeError('Service identity/data directory mismatch. No process stopped.')
    # Old source hashes are allowed deliberately: stopping a stale engine is how
    # updates recover. Check its checkout, process command and listening PID.
    command = subprocess.check_output(['ps', '-ww', '-p', str(pid), '-o', 'command='], text=True).strip()
    expected = str(repo / '.venv/bin/spatialstage')
    if not command.endswith(' ' + expected):
        raise RuntimeError('Process command does not match this checkout. No process stopped.')
    listeners = subprocess.check_output(['lsof', '-nP', f'-iTCP:{port}', '-sTCP:LISTEN', '-t'], text=True).split()
    if set(listeners) != {str(pid)}:
        raise RuntimeError('Listening PID mismatch. No process stopped.')
    status = get('audio/status')
    mixer = status.get('mixer') or {}
    simulation = status.get('simulation') or {}
    if (status.get('measurement_active') or mixer.get('voices') or simulation.get('recording')
            or status.get('preparing') or (status.get('connected') and
            (not mixer.get('master_mute') or not mixer.get('mute_settled')))):
        raise RuntimeError('Playback, capture, measurement, preload or unmuted output is active. Save work, stop capture/measurement, PANIC and wait for MAIN MUTE, then retry. No process stopped.')
    if get('health').get('runtime') != identity:
        raise RuntimeError('Service changed during verification. No process stopped.')
    # Recheck process identity immediately before signalling.
    if subprocess.check_output(['ps', '-ww', '-p', str(pid), '-o', 'command='], text=True).strip() != command:
        raise RuntimeError('Process changed during verification. No process stopped.')
    os.kill(pid, signal.SIGTERM)
    for _ in range(50):
        result = subprocess.run(['lsof', '-nP', f'-iTCP:{port}', '-sTCP:LISTEN', '-t'], capture_output=True, text=True)
        if str(pid) not in result.stdout.split():
            print(f'SpatialStage stopped normally (PID {pid}). You may start the main or simulation launcher.')
            return
        time.sleep(.1)
    raise RuntimeError('SIGTERM sent, but shutdown is still pending. No force-kill attempted; check before restarting.')


if __name__ == '__main__':
    try:
        stop_engine(Path(__file__).resolve().parents[1])
    except Exception as exc:
        print(f'Cannot safely stop SpatialStage: {exc}')
        raise SystemExit(1)
