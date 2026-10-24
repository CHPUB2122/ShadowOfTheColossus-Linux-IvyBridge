#!/usr/bin/env python3
"""Extract the pinned Arch build dependencies into out/deps, without sudo or pacman writes."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent.parent


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def main():
    lock = ROOT / 'packaging/linux/ivybridge-deps.lock.json'
    packages = json.loads(lock.read_text())['packages']
    cache = ROOT / 'out/deps/packages'
    prefix = ROOT / 'out/deps/arch-root'
    cache.mkdir(parents=True, exist_ok=True)
    prefix.mkdir(parents=True, exist_ok=True)
    for package in packages:
        filename = package['filename']
        if Path(filename).name != filename:
            raise ValueError('Invalid package filename')
        archive = cache / filename
        if not archive.is_file():
            temporary = archive.with_suffix(archive.suffix + '.tmp')
            urls = [package['url'],
                    f'https://archive.archlinux.org/packages/{package["name"][0]}/{package["name"]}/{filename}']
            try:
                for index, url in enumerate(urls):
                    try:
                        print(f'Downloading {package["name"]} {package["version"]}', flush=True)
                        with urllib.request.urlopen(url, timeout=60) as source, temporary.open('wb') as target:
                            shutil.copyfileobj(source, target)
                        break
                    except urllib.error.URLError:
                        if index == len(urls) - 1:
                            raise
                if digest(temporary) != package['sha256']:
                    raise ValueError(f'Package checksum mismatch: {filename}')
                temporary.replace(archive)
            finally:
                temporary.unlink(missing_ok=True)
        if digest(archive) != package['sha256']:
            raise ValueError(f'Cached package checksum mismatch: {filename}')
        # Extract only the package's usr/ tree, retaining no package-manager metadata.
        subprocess.run(['tar', '--extract', '--file', str(archive), '--directory', str(prefix),
                        '--no-same-owner', '--no-same-permissions', '--wildcards', 'usr/*'], check=True)
        print(f'Verified and extracted {package["name"]} {package["version"]}', flush=True)
    print(f'Local dependency prefix: {prefix / "usr"}')


if __name__ == '__main__':
    main()
