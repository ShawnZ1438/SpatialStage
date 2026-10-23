"""Render one GO (including its automatic chain) offline using the real controller."""
import argparse
import json
from pathlib import Path

from stagespatialcue.audio import StageController
from stagespatialcue.simulation import SimulationStream
from stagespatialcue.storage import ProjectStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=Path('SpatialStage-test-data'))
    parser.add_argument('--project', required=True)
    parser.add_argument('--index', type=int, default=0, help='Zero-based cue index')
    parser.add_argument('--seconds', type=float, default=6)
    parser.add_argument('--output', type=Path, default=Path('test-output/offline-4ch.wav'))
    args = parser.parse_args()
    if not 0 < args.seconds <= 60:
        parser.error('--seconds must be in (0, 60]')
    stage = StageController(ProjectStore(args.data))
    try:
        stage.arm(args.project, args.index)
        stream = SimulationStream(stage)
        stage.stream = stream
        stream.active = True  # deterministic manual stepping, no thread/device
        check = stage.preflight(args.project)
        if not check['ok']:
            raise ValueError(check['issues'])
        stage.mixer.master_mute = False  # file rendering only; no physical playback
        stream.capture(True)
        stage.go(args.project)
        remaining = round(args.seconds * 48000)
        while remaining:
            count = min(512, remaining)
            stream.step(count)
            remaining -= count
        stream.capture(False)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(stream.wav())
        report = {'project_id': args.project, 'cue_index':args.index,
                  'frames':stream.frames, 'channels':4, 'sample_rate':48000,
                  'peak_over_blocks':stage.mixer.peak_over_count,
                  'mode':'offline production controller/mixer; no hardware',
                  'note':'One GO and automatic chain only; manual later GOs are not invented.'}
        args.output.with_suffix('.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report))
    finally:
        stage.shutdown()


if __name__ == '__main__':
    main()
