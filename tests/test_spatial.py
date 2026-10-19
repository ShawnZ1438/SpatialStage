import numpy as np
import pytest
from pydantic import ValidationError

from stagespatialcue.models import Project, Speaker, ModPoint
from stagespatialcue.spatial import vbap_gains, envelope_offsets


def test_cardinal_angles_are_clockwise_from_twelve():
    speakers=Project().speakers
    expected={45:1,135:2,225:3,315:0}
    for angle,channel in expected.items():
        gains=vbap_gains(angle,speakers)[0]
        assert np.argmax(gains)==channel
        assert gains[channel]==pytest.approx(1.0, abs=1e-5)
    right = vbap_gains(90,speakers)[0]
    assert right[1]==pytest.approx(right[2], abs=1e-5)
    left = vbap_gains(270,speakers)[0]
    assert left[0]==pytest.approx(left[3], abs=1e-5)


def test_azimuth_wrap_and_constant_power():
    speakers=Project().speakers
    bearing=np.array([-720,0,0.01,45,90,180,270,359.99,360,720])
    gain=vbap_gains(bearing,speakers)
    assert gain.shape==(len(bearing),4)
    assert np.all(gain>=-1e-6)
    assert np.allclose(np.sum(gain**2,axis=1),1.0,atol=1e-5)
    assert np.allclose(gain[1],gain[-1])


def test_output_permutation_and_distance():
    p=Project()
    p.speakers[0].output_channel=4
    p.speakers[3].output_channel=1
    p.speakers[0].distance_m=6
    p.speakers[1].distance_m=3
    g=vbap_gains(315,p.speakers,distance_compensation=True)[0]
    assert g[3]>1
    assert g[0]==0


def test_reject_invalid_coverage_or_channel_duplicates():
    bad=[Speaker(name=str(i),angle_deg=10+i*10,distance_m=3,output_channel=i+1) for i in range(4)]
    with pytest.raises(ValidationError): Project(speakers=bad)
    bad=Project().speakers
    bad[0].output_channel=2
    with pytest.raises(ValidationError): Project(speakers=bad)


def test_modulation_offsets_unwrapped():
    time=np.array([0,0.5,1,1.5,2])
    points=[ModPoint(time_s=0,offset_deg=0),ModPoint(time_s=2,offset_deg=720)]
    assert np.allclose(envelope_offsets(time,points),[0,180,360,540,720])
