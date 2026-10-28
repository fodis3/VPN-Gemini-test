from pathlib import Path
import hashlib, io, json, urllib.request, zipfile
root = Path(__file__).resolve().parents[1]
(root / 'bin').mkdir(exist_ok=True)
for item in json.loads((root / 'cores.lock.json').read_text()):
    archive = zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(item['url'], timeout=120).read()))
    names = [n for n in archive.namelist() if Path(n).name == item['name']]
    assert len(names) == 1
    data = archive.read(names[0])
    assert hashlib.sha256(data).hexdigest() == item['sha256']
    (root / 'bin' / item['name']).write_bytes(data)
(root / 'artifacts').mkdir(exist_ok=True)
print('Verified Windows cores ready')
