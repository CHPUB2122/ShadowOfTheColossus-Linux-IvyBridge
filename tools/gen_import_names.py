#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Regenerate src/import_names.inc (NID -> symbol name) for the game's imports.

Keeps every existing entry and adds the imports of out/boot-linked.bin, named from a
shadPS4 aerolib.inl (public PS4 symbol lists). Entries are unscoped NIDs: the runtime
matches imports by NID alone.

usage: gen_import_names.py <aerolib.inl> [--out out] [--inc src/import_names.inc]
"""
import argparse
from pathlib import Path
import re
import struct


def linked_names(path):
    raw = path.read_bytes()
    magic, size, entry, ns, nr, ni, flags = struct.unpack_from('<8s6Q', raw, 0)
    if magic != b'BBPROBE5':
        raise SystemExit('expected out/boot-linked.bin (BBPROBE5) from link_modules.py')
    pos = 56 + 8 + 32
    modules, = struct.unpack_from('<Q', raw, pos)
    pos += 8 + modules * 56
    bindings, = struct.unpack_from('<Q', raw, pos)
    pos += 8 + bindings * 24 + ns * 24
    return [raw[pos + i * 128:pos + (i + 1) * 128].split(b'\0', 1)[0].decode() for i in range(ni)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('aerolib', type=Path)
    parser.add_argument('--out', type=Path, default=Path('out'))
    parser.add_argument('--inc', type=Path, default=Path('src/import_names.inc'))
    args = parser.parse_args()
    known = dict(re.findall(r'STUB\(\s*"([^"]+)"\s*,\s*([^\s)]+)\s*\)', args.aerolib.read_text(errors='replace')))
    lines = args.inc.read_text().splitlines()
    header = [line for line in lines if not line.startswith('{')]
    entries = dict(re.findall(r'^\{"([^"]+)","([^"]+)"\},$', '\n'.join(lines), re.M))
    added = missing = 0
    for name in linked_names(args.out / 'boot-linked.bin'):
        nid = name.split('#')[0]
        if nid in entries:
            continue
        if nid in known:
            entries[nid] = known[nid]
            added += 1
        else:
            missing += 1
    body = [f'{{"{nid}","{symbol}"}},' for nid, symbol in sorted(entries.items(), key=lambda e: e[1])]
    args.inc.write_text('\n'.join(header + body) + '\n', newline='\n')
    print(f'{len(entries)} names ({added} added, {missing} imports without a public name)')


if __name__ == '__main__':
    main()
