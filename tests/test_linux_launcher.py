"""Native launcher selection and subprocess flags, without a game dump or a window."""
from paths import ROOT
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location('native_sotc', ROOT / 'sotc.py')
sotc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sotc)


class NativeLauncherTests(unittest.TestCase):
    def test_linux_subprocess_flags(self):
        with mock.patch.object(sotc.os, 'name', 'posix'):
            self.assertEqual(sotc.no_console(), 0)
            with mock.patch.object(sotc.subprocess, 'run', return_value=SimpleNamespace(returncode=0)) as run:
                sotc.run_script('prepare.py', 'fixture')
                self.assertEqual(run.call_args.kwargs['creationflags'], 0)
                self.assertEqual(run.call_args.args[0][-1], 'fixture')

    def test_native_binary_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'out').mkdir()
            native = root / 'out' / 'bb-probe'
            native.touch()
            with mock.patch.object(sotc, 'PORT', root), mock.patch.object(sotc.os, 'name', 'posix'):
                self.assertEqual(sotc.find_probe(), native)

    def test_windows_binary_selection_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'bin').mkdir()
            binary = root / 'bin' / 'bb-probe.exe'
            binary.touch()
            with mock.patch.object(sotc, 'PORT', root), mock.patch.object(sotc.os, 'name', 'nt'):
                self.assertEqual(sotc.find_probe(), binary)

    def test_linux_does_not_select_a_windows_binary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'out').mkdir()
            (root / 'out' / 'bb-probe.exe').touch()
            with mock.patch.object(sotc, 'PORT', root), mock.patch.object(sotc.os, 'name', 'posix'), \
                    mock.patch('sys.stderr', new_callable=io.StringIO) as error:
                with self.assertRaises(SystemExit):
                    sotc.find_probe()
                self.assertIn('bb-probe not found', error.getvalue())

    @unittest.skipUnless(os.name == 'posix' and (ROOT / 'out/bb-probe').is_file(), 'needs native Linux build')
    def test_native_loader_keeps_the_cpu_guard(self):
        flags = set(Path('/proc/cpuinfo').read_text().split())
        supported = {'avx', 'bmi1', 'movbe'} <= flags and bool({'abm', 'lzcnt'} & flags)
        result = subprocess.run([str(ROOT / 'out/bb-probe'), 'nonexistent-fixture', '--cpu-only'],
                                capture_output=True, text=True, timeout=10,
                                env={**os.environ, 'LD_BIND_NOW': '1'}, cwd=tempfile.gettempdir())
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('cannot open boot file' if supported else 'This CPU is not supported', result.stderr)

    @unittest.skipUnless((ROOT / 'out/bb-probe').is_file(), 'needs native Linux build')
    def test_native_elf_artifacts(self):
        for relative, elf_type in [('out/bb-probe', 2), ('out/gpu/libbbgpu.so', 3)]:
            with self.subTest(artifact=relative):
                with (ROOT / relative).open('rb') as stream:
                    header = stream.read(20)
                self.assertEqual(header[:6], b'\x7fELF\x02\x01')  # ELF64, little endian
                self.assertEqual(struct.unpack_from('<HH', header, 16), (elf_type, 62))  # x86-64
