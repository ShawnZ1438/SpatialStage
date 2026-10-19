"""Create a synthetic short demo show; never substitute this for stage calibration."""
from pathlib import Path
import argparse
import numpy as np
import soundfile as sf

from stagespatialcue.models import Cue, ModPoint
from stagespatialcue.storage import ProjectStore


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("~/.stagespatialcue/projects").expanduser())
    args = parser.parse_args()
    store = ProjectStore(args.data)
    project = store.create("DEMO — Spatial rehearsal")
    fs = 48_000
    for n, (name, angle) in enumerate([("Front sweep", 0.0), ("Behind actor", 180.0), ("Left cue", 270.0)], 1):
        sec = 2.0 + n
        time = np.arange(int(fs * sec)) / fs
        env = np.sin(np.pi * time / sec) ** 2
        audio = (0.08 * np.sin(2 * np.pi * (220 + n * 90) * time) * env).astype(np.float32)
        filename = f"{n:03d}_{name.replace(' ','_')}.wav"
        path = store.directory(project.id) / "media" / filename
        path.parent.mkdir(exist_ok=True)
        sf.write(path, audio, fs)
        project.cues.append(Cue(
            title=name, filename=filename, media_relpath=f"media/{filename}",
            duration_s=sec, position_deg=angle,
            modulation=[ModPoint(time_s=0,offset_deg=0), ModPoint(time_s=sec,offset_deg=120)] if n==1 else [ModPoint(time_s=0,offset_deg=0)],
            start_mode="layer" if n==2 else "replace",
        ))
    store.save(project)
    print(f"Created {project.name} (ID {project.id}) under {store.directory(project.id)}")

if __name__ == "__main__":
    main()
