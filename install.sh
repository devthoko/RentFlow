#!/usr/bin/env bash
set -euo pipefail
if [ "$(id -u)" -ne 0 ]; then echo "Bitte als root oder mit sudo ausführen." >&2; exit 1; fi
if ! command -v python3 >/dev/null || ! command -v curl >/dev/null; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update < /dev/null
  apt-get install -y python3 curl ca-certificates < /dev/null
fi
python3 - "$@" <<'PY'
import argparse,hashlib,json,os,re,subprocess,tarfile,tempfile,urllib.request
from pathlib import Path
p=argparse.ArgumentParser(description='Geprüfte RentFlow-Version installieren')
p.add_argument('--version',default='1.0.0-rc.1')
p.add_argument('--archive',help='Lokales Release-Archiv für isolierte Tests')
p.add_argument('--sha256')
p.add_argument('--isolated',action='store_true')
p.add_argument('--upgrade',action='store_true')
p.add_argument('--prefix',default='/opt/rentflow')
p.add_argument('--base-url',default='')
a=p.parse_args()
if not re.fullmatch(r'\d+\.\d+\.\d+(?:-rc\.\d+)?',a.version):p.error('Ungültige Versionsnummer')
headers={'User-Agent':'RentFlow-Installer'}
if os.getenv('GITHUB_TOKEN'):headers['Authorization']='Bearer '+os.environ['GITHUB_TOKEN']
def fetch(url):
 with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=60) as response:
  result=response.read(150*1024*1024+1)
  if len(result)>150*1024*1024:raise ValueError('Download ist zu groß.')
  return result
with tempfile.TemporaryDirectory(prefix='rentflow-release-') as tmp:
 root=Path(tmp)
 if a.archive:
  if not a.sha256:p.error('--archive benötigt --sha256')
  content=Path(a.archive).read_bytes();digest=a.sha256
 else:
  info=json.loads(fetch('https://raw.githubusercontent.com/devthoko/RentFlow/main/releases/'+a.version+'.json'))
  if info.get('version')!=a.version or not re.fullmatch('[0-9a-f]{40}',info.get('commit','')):raise ValueError('Ungültiges Release-Manifest.')
  digest=info['sha256'];content=fetch('https://codeload.github.com/devthoko/RentFlow/tar.gz/'+info['commit'])
 if not re.fullmatch('[0-9a-f]{64}',digest) or hashlib.sha256(content).hexdigest()!=digest:raise ValueError('Release-Prüfsumme stimmt nicht. Installation abgebrochen.')
 archive=root/'release.tar.gz';archive.write_bytes(content)
 with tarfile.open(archive,'r:gz') as tf:
  entries=tf.getmembers()
  if sum(e.size for e in entries)>500*1024*1024:raise ValueError('Archiv ist zu groß.')
  for e in entries:
   q=Path(e.name)
   if q.is_absolute() or '..' in q.parts or not (e.isdir() or e.isfile()):raise ValueError('Unsicheres Release-Archiv.')
  tf.extractall(root/'source',filter='data')
 dirs=list((root/'source').iterdir())
 if len(dirs)!=1 or not dirs[0].is_dir():raise ValueError('Ungültige Release-Struktur.')
 source=dirs[0]
 import tomllib
 actual=tomllib.loads((source/'pyproject.toml').read_text())['project']['version']
 if actual!=a.version:raise ValueError('Version im Archiv stimmt nicht mit der angeforderten Version überein.')
 command=['python3',str(source/'scripts/manage.py'),'upgrade' if a.upgrade else 'install','--source',str(source),'--prefix',a.prefix]
 if a.isolated:command+=['--isolated']
 if a.base_url:command+=['--base-url',a.base_url]
 subprocess.run(command,check=True)
PY
