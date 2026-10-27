import json
import numpy as np
import soundfile as sf
from stagespatialcue.bundle import sync_bundled_show
from stagespatialcue.storage import ProjectStore


def test_manifest_titles_and_sync_preserve_ids_parameters_and_order(tmp_path):
    root=tmp_path/'show';(root/'audio').mkdir(parents=True)
    names=['05_合唱.wav','02_鸟声.wav']
    for name in names:sf.write(root/'audio'/name,np.zeros(100),48000)
    (root/'cue-manifest.json').write_text(json.dumps({n:{'title':n[:2]+' · mapped'} for n in names}))
    store=ProjectStore(tmp_path/'data');first=sync_bundled_show(store,root)
    assert [c.title for c in first.cues]==['02 · mapped','05 · mapped']
    first.cues.reverse();first.cues[0].gain_db=-23;first.cues[0].title='operator edit';store.save(first)
    again=sync_bundled_show(store,root)
    assert again.model_dump()==first.model_dump()
