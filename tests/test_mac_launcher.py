"""Exercise the Finder/home-directory launcher flow without binding a server."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]

@pytest.mark.skipif(not shutil.which('zsh'), reason='Mac launcher requires zsh')
def test_launcher_from_home_without_pythonpath(tmp_path):
    repo = tmp_path/'checkout with spaces';repo.mkdir()
    for name in ['run_mac.command','Start SpatialStage.command','pyproject.toml']:
        shutil.copy2(ROOT/name,repo/name)
    (repo/'stagespatialcue').symlink_to(ROOT/'stagespatialcue',target_is_directory=True)
    bin_dir=repo/'.venv/bin';bin_dir.mkdir(parents=True)
    (bin_dir/'python').symlink_to(sys.executable)
    (bin_dir/'activate').write_text('export PATH="'+str(bin_dir)+':$PATH"\n')
    (repo/'.venv/.spatialstage-install').write_text(hashlib.sha256((repo/'pyproject.toml').read_bytes()).hexdigest()+'\n')
    scripts={
        'curl':'#!/bin/sh\nexit 1\n',
        'lsof':'#!/bin/sh\nexit 1\n',
        'open':'#!/bin/sh\nexit 0\n',
        'caffeinate':'#!/bin/sh\nshift\nexec "$@"\n',
        'spatialstage':'''#!/bin/sh
exec python -c 'import os, stagespatialcue; from pathlib import Path; assert Path.cwd() == Path(os.environ["EXPECTED_CHECKOUT"]); assert os.environ["PYTHONPATH"].split(":")[0] == str(Path.cwd()); assert Path(stagespatialcue.__file__).parent == Path.cwd()/"stagespatialcue"; print("CHECKOUT_RESOLVED")'
''',
    }
    for name,content in scripts.items():
        path=bin_dir/name;path.write_text(content);path.chmod(0o755)
    env=dict(os.environ,EXPECTED_CHECKOUT=str(repo));env.pop('PYTHONPATH',None)
    result=subprocess.run(['zsh',str(repo/'Start SpatialStage.command')],cwd=Path.home(),env=env,text=True,capture_output=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
    assert 'CHECKOUT_RESOLVED' in result.stdout
