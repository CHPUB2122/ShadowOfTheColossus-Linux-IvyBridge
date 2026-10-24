"""Production/diagnostic launch contract and child lifecycle, without GPU/game data."""
from paths import ROOT
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('native_play', ROOT / 'tools/sotc_launch.py')
play = importlib.util.module_from_spec(spec)
spec.loader.exec_module(play)
frame_spec = importlib.util.spec_from_file_location('frame_report', ROOT / 'tools/sotc_frame_report.py')
frame_report = importlib.util.module_from_spec(frame_spec)
frame_spec.loader.exec_module(frame_report)


class NativePlayTests(unittest.TestCase):
    def fixture(self, root):
        (root / 'game').mkdir()
        (root / 'game/eboot.bin').touch()
        (root / 'out/gpu').mkdir(parents=True)
        for name in (*play.ARTIFACTS, 'gpu/libbbgpu.so'):
            (root / 'out' / name).write_bytes(b'fixture')
        user = root / 'profile with spaces'
        user.mkdir()
        return user

    def test_profile_selection_and_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env = {'SOTC_USER_DIR': 'new', 'BB_GPU_USER_DIR': 'old'}
            with self.assertRaisesRegex(ValueError, 'different profiles'):
                play.resolve_storage(env, root=root)
            user = play.resolve_storage(env, 'chosen', root=root)
            self.assertEqual(user, root / 'chosen')
            self.assertEqual(env['SOTC_USER_DIR'], env['BB_GPU_USER_DIR'])
            env = {'BB_GPU_USER_DIR': 'existing'}
            self.assertEqual(play.resolve_storage(env, root=root), root / 'existing')

    def test_real_child_saves_backup_exit_and_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            user = self.fixture(root)
            saves = user / 'savedata/1/CUSA08809/Profile'
            saves.mkdir(parents=True)
            (saves / 'USR-DATA').write_text('old')
            binary = root / 'out/bb-probe'
            binary.write_text('#!' + sys.executable + '\n' +
                              'import os,sys,pathlib\n'
                              'u=pathlib.Path(sys.argv[sys.argv.index("--user")+1])\n'
                              'assert str(u)==os.environ["BB_GPU_USER_DIR"]\n'
                              'assert sys.argv[-2:]==["--timeout","0"]\n'
                              '(u/"savedata/1/CUSA08809/Profile/USR-DATA").write_text("new")\n'
                              'print("fixture closed normally")\n')
            binary.chmod(0o755)
            env = os.environ.copy()
            play.resolve_storage(env, user, root)
            command = play.prepared_command(root / 'game', user, root)
            with play.user_lock(user):
                with self.assertRaisesRegex(ValueError, 'another session'):
                    with play.user_lock(user):
                        self.fail('concurrent profile accepted')
            self.assertEqual(play.play(command, env, user, root), 0)
            logs = next((root / 'out/logs').iterdir())
            self.assertEqual((logs / 'savedata-before/1/CUSA08809/Profile/USR-DATA').read_text(), 'old')
            self.assertEqual((saves / 'USR-DATA').read_text(), 'new')
            result = json.loads((logs / 'result.json').read_text())
            self.assertEqual(result['termination'], 'exit')
            self.assertEqual(result['changed_save_files'], ['1/CUSA08809/Profile/USR-DATA'])
            for name in (*play.ARTIFACTS[1:], 'gpu/libbbgpu.so'):
                self.assertEqual((root / 'out' / name).read_bytes(), b'fixture')

    @unittest.skipUnless((ROOT / 'out/bb-probe').is_file(), 'needs native artifacts')
    def test_real_dry_run_disables_inherited_instrumentation(self):
        with tempfile.TemporaryDirectory() as tmp:
            game = Path(tmp) / 'game'
            game.mkdir(); (game / 'eboot.bin').touch()
            user = Path(tmp) / 'uncreated-profile'
            env = {**os.environ, **dict.fromkeys(play.DIAGNOSTICS, '1'),
                   'BB_FRAME_DUMP_TRIGGER': 'old-trigger', 'SOTC_CP_THREADS': '0', 'SOTC_RECORD_THREAD': '0'}
            result = subprocess.run([sys.executable, str(ROOT / 'tools/sotc_launch.py'),
                                     '--game', str(game), '--user', str(user), '--dry-run'],
                                    cwd='/', env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(data['command'][-2:], ['--timeout', '0'])
            self.assertEqual(data['environment']['BB_GPU_USER_DIR'], str(user))
            self.assertEqual(data['environment']['SOTC_FRAME_LOG'], '0')
            self.assertNotIn('SOTC_PASS_TRACE', data['environment'])
            self.assertNotIn('BB_FRAME_DUMP_TRIGGER', data['environment'])
            self.assertNotIn('SOTC_CMD_STATS', data['environment'])
            self.assertNotIn('SOTC_FPS', data['environment'])
            self.assertEqual(data['environment']['SOTC_CP_THREADS'], '1')
            self.assertEqual(data['environment']['SOTC_RECORD_THREAD'], '1')
            self.assertFalse(user.exists())

    def test_signal_statuses_are_distinct(self):
        self.assertEqual(play.shell_status(-11), 139)
        self.assertEqual(play.termination(-11), 'sigsegv')
        self.assertEqual(play.termination(139), 'sigsegv')
        self.assertEqual(play.termination(142), 'sigalrm')
        self.assertEqual(play.termination(0), 'exit')

    def test_frame_report_counts_intervals_and_rejects_false_percentiles(self):
        one = '\n'.join(f'SOTCFRAME {i} t={i*50}ms us={i*50000}' for i in range(1, 5))
        report = frame_report.report(one)
        self.assertEqual(report['frames'], 3)
        self.assertEqual(report['fps'], 20)
        self.assertEqual(report['p99_ms'], 50)
        grouped = one.replace('SOTCFRAME 2 ', 'SOTCFRAME 30 ').splitlines()[:2]
        report = frame_report.report('\n'.join(grouped))
        self.assertIn('percentiles_unavailable', report)
        self.assertNotIn('p99_ms', report)
        with self.assertRaises(ValueError):
            frame_report.report('no frames recorded')
