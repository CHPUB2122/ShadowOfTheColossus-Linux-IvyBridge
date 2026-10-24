"""Exercise the actual loader deadline on an Ivy Bridge compatible synthetic guest."""
from paths import ROOT
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest


@unittest.skipUnless((ROOT / 'out/bb-probe').is_file(), 'needs Linux loader')
class DeadlineTests(unittest.TestCase):
    def test_absolute_deadline_is_opt_in(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # One executable entry in a valid EH table. This runs the real CPU scanner.
            table = struct.pack('<4BIIii', 1, 0x1b, 3, 0x3b, 0, 1, -4096, 0)
            image = (b'\xeb\xfe' + b'\x90' * 4094) + table.ljust(4096, b'\0')
            boot = root / 'boot.bin'
            boot.write_bytes(struct.pack('<8s5Q', b'BBPROBE1', 8192, 0, 2, 0, 0) +
                             struct.pack('<6Q', 0, 4096, 5, 4096, 4096, 4) + image)
            cpu = root / 'cpu.bin'
            cpu.write_bytes(struct.pack('<8s3Q', b'SOTCCPU1', 4096, len(table), 0))
            user = root / 'user'; user.mkdir()
            env = {**os.environ, 'BB_GPU_USER_DIR': str(user)}
            command = [str(ROOT / 'out/bb-probe'), str(boot), '--cpu-only', '--sotc-cpu', str(cpu)]
            explicit = subprocess.run(command + ['--timeout', '1'], env=env,
                                      capture_output=True, timeout=5)
            self.assertEqual(explicit.returncode, 142, explicit.stdout + explicit.stderr)
            self.assertIn(b'STOP: watchdog timeout', explicit.stderr)
            with subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
                try:
                    with self.assertRaises(subprocess.TimeoutExpired):
                        process.communicate(timeout=11)
                finally:
                    process.terminate()
                    stdout, stderr = process.communicate(timeout=5)
                self.assertNotIn(b'STOP: watchdog timeout', stderr)
                self.assertIn(b'Entering original x86-64 code', stdout)
