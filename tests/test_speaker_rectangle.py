import copy
import json
import math
from unittest.mock import patch
import pytest
from stagespatialcue.models import Project
from stagespatialcue.speaker_rectangle import rectangle_speakers, migrate


def test_rectangle_retains_center_orientation_mapping_and_programming(tmp_path):
    p=Project(name='local programming').model_dump()
    # Rotate and translate the existing rectangle to prove no global-axis guess.
    for s in p['speakers']:
        a=math.radians(s['angle_deg']+20)
        x,y=3*math.sin(a)+.3,3*math.cos(a)-.2
        s.update(angle_deg=math.degrees(math.atan2(x,y))%360,distance_m=math.hypot(x,y))
    p.update(calibration_enabled=True,active_calibration_id='local-calibration',global_rotation_deg=17,master_db=-9)
    for i,s in enumerate(p['speakers']):s['trim_db']=-i
    before=copy.deepcopy(p)
    new=rectangle_speakers(p['speakers'])
    xy={s['output_channel']:(s['distance_m']*math.sin(math.radians(s['angle_deg'])),s['distance_m']*math.cos(math.radians(s['angle_deg']))) for s in new}
    assert math.dist(xy[1],xy[2])==pytest.approx(8.65)
    assert math.dist(xy[2],xy[3])==pytest.approx(6.47)
    assert math.dist(xy[3],xy[4])==pytest.approx(8.65)
    assert math.dist(xy[1],xy[4])==pytest.approx(6.47)
    assert tuple(sum(x[k] for x in xy.values())/4 for k in (0,1))==pytest.approx((.3,-.2))
    assert p==before
    for old,speaker in zip(p['speakers'],new):
        assert {k:v for k,v in old.items() if k not in ['angle_deg','distance_m']}=={k:v for k,v in speaker.items() if k not in ['angle_deg','distance_m']}
    path=tmp_path/'project.json';path.write_text(json.dumps(p));original=path.read_bytes()
    migrate(path);assert path.read_bytes()==original
    with patch('stagespatialcue.speaker_rectangle.socket.socket') as sock:
        sock.return_value.__enter__.return_value.connect_ex.return_value=1
        migrate(path,True)
    updated=json.loads(path.read_text());assert updated.pop('speakers')==new
    before.pop('speakers');assert updated==before
    assert next(tmp_path.glob('*.before-speaker*')).read_bytes()==original
    assert [s["distance_m"] for s in rectangle_speakers(new)]==pytest.approx([s["distance_m"] for s in new])


def test_refuses_ambiguous_numbering():
    speakers=[s.model_dump() for s in Project().speakers]
    speakers[1]['angle_deg']=130
    with pytest.raises(ValueError,match='numbering'):rectangle_speakers(speakers)


def test_refuses_active_service_without_writing(tmp_path):
    path=tmp_path/'project.json';path.write_text(Project().model_dump_json());original=path.read_bytes()
    with patch('stagespatialcue.speaker_rectangle.socket.socket') as sock:
        sock.return_value.__enter__.return_value.connect_ex.return_value=0
        with pytest.raises(RuntimeError,match='active'):migrate(path,True)
    assert path.read_bytes()==original and not list(tmp_path.glob('*.before-speaker*'))
