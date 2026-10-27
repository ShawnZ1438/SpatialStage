"""Every interface string key used by the page exists in both 中文 and English."""
import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / 'stagespatialcue' / 'static'


def dictionary(lang):
    source = (STATIC / 'i18n.js').read_text(encoding='utf-8')
    block = re.search(rf'const {lang} = \{{(.*?)\n  \}};', source, re.S).group(1)
    return set(re.findall(r"(?:^|,)\s*([A-Za-z][A-Za-z0-9]*):'", block, re.M))


def used_keys():
    keys = set()
    for name in ('app.js', 'editor.js', 'simulation.js'):
        source = (STATIC / name).read_text(encoding='utf-8')
        keys |= set(re.findall(r"\bt\('([A-Za-z0-9]+)'", source))
        # t({a:'key', ...}[x]) and t(cond ? 'a' : 'b') lookups
        for call in re.findall(r"\bt\(([^()]*(?:\([^()]*\)[^()]*)*)\)", source):
            if call.startswith("'"):
                continue
            keys |= {k for k in re.findall(r"'([A-Za-z][A-Za-z0-9]+)'", call) if not k.islower() or k in {'off', 'loop', 'close'}}
        # [['field', 'key'], ...] tables passed to t(key)
        keys |= set(re.findall(r"\['[a-z_]+', '([a-z]+[A-Z][A-Za-z]*)'\]", source))
    html = (STATIC / 'index.html').read_text(encoding='utf-8')
    keys |= set(re.findall(r'data-i18n(?:-[a-z]+)?="([A-Za-z0-9]+)"', html))
    return keys


def test_every_used_key_has_both_languages():
    zh, en = dictionary('zh'), dictionary('en')
    used = used_keys() - {'replace', 'layer', 'queue', 'manual', 'path', 'keyframes', 'adsr', 'width', 'mono',
                          'crossfade', 'cut', 'virtual', 'sum', 'none', 'stored', 'changed', 'dirty', 'saving',
                          'saved', 'error', 'position', 'add', 'auto_continue', 'auto_follow'} | {'saving', 'saved'}
    assert not used - zh, f'missing 中文: {sorted(used - zh)}'
    assert not used - en, f'missing English: {sorted(used - en)}'
    assert zh == en, f'only in one language: {sorted(zh ^ en)}'
