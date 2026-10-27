from stagespatialcue import runtime


def test_identity_detects_source_and_data_changes(tmp_path, monkeypatch):
    root = tmp_path / 'checkout'
    package = root / 'stagespatialcue'
    (package / 'static').mkdir(parents=True)
    (root / 'pyproject.toml').write_text('[project]')
    source = package / 'server.py'
    source.write_text('old')
    monkeypatch.setattr(runtime, '__file__', str(package / 'runtime.py'))
    first = runtime.runtime_identity(tmp_path / 'show')
    again = runtime.runtime_identity(tmp_path / 'show')
    assert first == again
    assert runtime.runtime_identity(tmp_path / 'simulation')['data_root'] != first['data_root']
    source.write_text('new')
    assert runtime.runtime_identity(tmp_path / 'show')['source_sha256'] != first['source_sha256']
    assert first['source_sha256'] == again['source_sha256']
