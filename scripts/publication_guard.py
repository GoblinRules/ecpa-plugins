"""Focused public-source/artifact privacy guard. Prints locations, never matches."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parents[1]
PRIVATE_NAMES={'machines.json','machines.before.json','connections.json','gateway-runtime.json','mcp-services.json','oauth.json','credentials.json','id_rsa','id_ed25519','.env'}


def findings(path,data):
    errors=[]
    if any(part in {'test-artifacts','userdata','.venv','__pycache__'} for part in Path(path).parts):errors.append('local runtime/test artifact directory')
    if Path(path).name in PRIVATE_NAMES:errors.append('private configuration/key filename')
    # Current account/checkout paths are publication metadata too, not just API keys.
    for folder in {str(Path.home()),Path.home().as_posix()}:
        if folder.encode().lower() in data.lower() or folder.encode('utf-16-le').lower() in data.lower():
            errors.append('personal build/home path');break
    if re.search(rb'-----BEGIN (?:OPENSSH |RSA |EC |DSA |ENCRYPTED )?PRIVATE KEY-----',data):
        # Source parsers/tests legitimately refer to PEM marker strings. Only real bodies count.
        if re.search(rb'-----BEGIN [A-Z ]*PRIVATE KEY-----\s+[A-Za-z0-9+/=\r\n]{80,}',data):errors.append('private key body')
    return [f'{path}: {reason}' for reason in errors]


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--asset',action='append',default=[]);args=parser.parse_args()
    names=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0');errors=[]
    for name in filter(None,names):
        path=ROOT/name
        if path.is_file():errors.extend(findings(name,path.read_bytes()))
    for name in args.asset:
        path=Path(name)
        if path.suffix.lower()=='.zip':
            with zipfile.ZipFile(path) as archive:
                for member in archive.infolist():
                    if not member.is_dir():errors.extend(findings(path.name+'/'+member.filename,archive.read(member)))
        else:errors.extend(findings(path.name,path.read_bytes()))
    if errors:
        print('\n'.join(sorted(set(errors))));raise SystemExit(1)
    print('Publication boundary checked: no private configuration filenames, private key bodies or current developer-home paths found.')


if __name__=='__main__':main()
