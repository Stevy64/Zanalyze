"""La distribution embarquée est identifiée et installée sans divergence."""
import hashlib
import json
from pathlib import Path
import zipfile
import engine


def test_distribution_et_code_installe_correspondent_au_manifeste():
    vendor = Path(__file__).resolve().parents[2] / 'vendor'
    manifest = json.loads((vendor / 'engine-manifest.json').read_text(encoding='utf-8'))
    wheel = vendor / manifest['wheel']
    assert hashlib.sha256(wheel.read_bytes()).hexdigest() == manifest['sha256']
    assert engine.__version__ == manifest['version']
    installed = Path(engine.__file__).parent.parent
    with zipfile.ZipFile(wheel) as package:
        for name, digest in manifest['files'].items():
            assert hashlib.sha256(package.read(name)).hexdigest() == digest
            assert hashlib.sha256((installed / name).read_bytes()).hexdigest() == digest
