#!/usr/bin/env python3
"""Audit the actual CMake compiler commands and compiler ISA macros for Linux stage 1."""
import json
from pathlib import Path
import shlex
import subprocess
import sys


def main():
    database = Path(sys.argv[1])
    entries = json.loads(database.read_text())
    baseline = {'-march=ivybridge', '-mno-avx2', '-mno-bmi', '-mno-bmi2', '-mno-movbe', '-mno-lzcnt'}
    forbidden_macros = {'__AVX2__', '__BMI__', '__BMI2__', '__MOVBE__', '__LZCNT__'}
    configurations = set()
    for entry in entries:
        command = entry.get('arguments') or shlex.split(entry['command'])
        missing = baseline - set(command)
        if missing:
            raise RuntimeError(f'{entry["file"]}: missing baseline flags {sorted(missing)}')
        if any(arg.startswith(('-flto', '-fprofile-generate', '-fprofile-use')) for arg in command):
            raise RuntimeError(f'{entry["file"]}: PGO/LTO is enabled')
        # Preserve the order of all -m options: a dependency could override the baseline.
        isa_flags = tuple(arg for arg in command[1:] if arg.startswith('-m'))
        language = 'c' if entry['file'].endswith('.c') else 'c++'
        configurations.add((command[0], language, isa_flags))
    for compiler, language, flags in sorted(configurations):
        result = subprocess.run([compiler, *flags, '-dM', '-E', '-x', language, '-'],
                                input='', capture_output=True, text=True, check=True)
        macros = {line.split()[1] for line in result.stdout.splitlines() if line.startswith('#define ')}
        if forbidden_macros & macros or '__AVX__' not in macros:
            raise RuntimeError(f'{compiler} ({language}): unexpected CPU features {forbidden_macros & macros}')
    print(f'PASS: {len(entries)} compiler commands, {len(configurations)} ISA configurations; Ivy Bridge, PGO/LTO off')


if __name__ == '__main__':
    main()
