"""Explicit offline speaker-only migration; never imports a repository show over one."""
from __future__ import annotations
import argparse
import copy
import json
import math
import os
import socket
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from .models import Project


def rectangle_speakers(speakers, edge12=8.65, edge23=6.47):
    by_channel = {s['output_channel']: s for s in speakers}
    if set(by_channel) != {1, 2, 3, 4}:
        raise ValueError('Expected exactly channels 1–4')
    xy = {i: (s['distance_m'] * math.sin(math.radians(s['angle_deg'])),
              s['distance_m'] * math.cos(math.radians(s['angle_deg']))) for i, s in by_channel.items()}
    def unit(a, b):
        x, y = xy[b][0]-xy[a][0], xy[b][1]-xy[a][1]
        d = math.hypot(x, y)
        if d < .001:
            raise ValueError('Coincident speakers; verify numbering first')
        return x/d, y/d
    u, v = unit(1, 2), unit(1, 4)
    if abs(u[0]*v[0]+u[1]*v[1]) > .01 or math.dist(
            (xy[1][0]+xy[3][0], xy[1][1]+xy[3][1]),
            (xy[2][0]+xy[4][0], xy[2][1]+xy[4][1])) > .02:
        raise ValueError('Existing numbering is not a rectangle; inspect channel orientation first')
    center = tuple(sum(p[k] for p in xy.values())/4 for k in (0, 1))
    signs = {1:(-1,-1), 2:(1,-1), 3:(1,1), 4:(-1,1)}
    result = copy.deepcopy(speakers)
    for s in result:
        a,b = signs[s['output_channel']]
        x,y = (center[k]+a*edge12/2*u[k]+b*edge23/2*v[k] for k in (0,1))
        s.update(angle_deg=math.degrees(math.atan2(x,y))%360, distance_m=math.hypot(x,y))
    return result


def migrate(path: Path, apply=False):
    original = path.read_bytes()
    data = json.loads(original)
    updated = copy.deepcopy(data)
    updated['speakers'] = rectangle_speakers(data['speakers'])
    Project.model_validate(updated)
    print(json.dumps(updated['speakers'], ensure_ascii=False, indent=2))
    if not apply:
        print('Preview only. Save and close SpatialStage before --apply.')
        return
    # Refuse while a local service may be writing this project (including an
    # unknown service). User must also close browser tabs before applying.
    with socket.socket() as sock:
        if sock.connect_ex(('127.0.0.1',8765)) == 0:
            raise RuntimeError('Port 8765 is active. Save, close tabs, and stop SpatialStage first.')
    if path.read_bytes() != original:
        raise RuntimeError('Project changed during preview; retry after saving and stopping')
    backup = path.with_name(path.name+'.before-speaker-rectangle-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    with backup.open('xb') as f:
        f.write(original)
    fd, temporary = tempfile.mkstemp(prefix='.speaker-', dir=path.parent)
    try:
        with os.fdopen(fd,'w') as f:
            json.dump(updated,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
        os.replace(temporary,path)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)
    print(f'Applied speakers only. Exact original backup: {backup}')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project',type=Path,help='Exact local project.json, not the repository template')
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args();migrate(args.project,args.apply)

if __name__=='__main__':main()
