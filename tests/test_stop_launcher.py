"""Exercise stop guards against an isolated real loopback process, no audio."""
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import urlopen
import pytest


def test_stop_guards_and_sigterm(tmp_path):
    spec=importlib.util.spec_from_file_location('stopper',Path(__file__).parents[1]/'scripts/stop_spatialstage.py')
    stopper=importlib.util.module_from_spec(spec);spec.loader.exec_module(stopper)
    repo=tmp_path/'checkout';entry=repo/'.venv/bin/spatialstage';entry.parent.mkdir(parents=True)
    config=tmp_path/'fixture.json'
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    entry.write_text('''import json,os\nfrom http.server import BaseHTTPRequestHandler,HTTPServer\nclass Handler(BaseHTTPRequestHandler):\n def do_GET(self):\n  data=json.load(open(os.environ["STOP_FIXTURE"]))\n  value=data["health" if self.path.endswith("health") else "status"]\n  if self.path.endswith("health"): value["runtime"]["pid"]=os.getpid()\n  self.send_response(200);self.end_headers();self.wfile.write(json.dumps(value).encode())\n def log_message(self,*args): pass\nHTTPServer(("127.0.0.1",int(os.environ["STOP_PORT"])),Handler).serve_forever()\n''')
    health={'features':['simulation'],'runtime':{'source_root':str(repo),'source_sha256':'a'*64,'data_root':str(repo/'SpatialStage-test-data')}}
    status={'connected':True,'mixer':{'master_mute':True,'mute_settled':True,'voices':[]},'simulation':{'recording':False}}
    def save(): config.write_text(json.dumps({'health':health,'status':status}))
    save()
    process=subprocess.Popen([sys.executable,str(entry)],env={**os.environ,'STOP_FIXTURE':str(config),'STOP_PORT':str(port)})
    try:
        for _ in range(50):
            try:
                with urlopen(f'http://127.0.0.1:{port}/api/health',timeout=.2): break
            except OSError: time.sleep(.05)
        for target,key,value in [(health['runtime'],'source_root','/wrong'),(health['runtime'],'data_root','/wrong'),(health['runtime'],'source_sha256','invalid'),(status,'measurement_active',True),(status,'preparing',True),(status['mixer'],'voices',[{'playing':True}]),(status['mixer'],'master_mute',False),(status['simulation'],'recording',True)]:
            original=target.get(key);target[key]=value;save()
            with pytest.raises(RuntimeError): stopper.stop_engine(repo,port)
            assert process.poll() is None
            if original is None: del target[key]
            else: target[key]=original
        save()
        # Test verifies a stale but valid source hash may still be safely stopped.
        stopper.stop_engine(repo,port)
        process.wait(timeout=5)
        assert process.returncode == -15
    finally:
        if process.poll() is None: process.terminate();process.wait(timeout=5)
