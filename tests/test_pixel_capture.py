#!/usr/bin/env python3
"""Exercise the real preload helper against a fake RenderDoc API, without Vulkan."""
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "out/graphics-pixel/capture-hook.so"


class CaptureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.temp.name)
        (cls.path / "api.c").write_text(r'''
#include <stdio.h>
#include <stdlib.h>
#include "renderdoc_app.h"
static void path(const char *s) { (void)s; }
static unsigned count(void) { return 0; }
static void trigger(unsigned n) {
    FILE *f = fopen(getenv("TEST_EVENTS"), "a");
    fprintf(f, "%u\n", n); fclose(f);
}
static RENDERDOC_API_1_6_0 api = {
    .SetCaptureFilePathTemplate = path, .GetNumCaptures = count,
    .TriggerMultiFrameCapture = trigger,
};
int RENDERDOC_GetAPI(RENDERDOC_Version version, void **out) {
    if (version != eRENDERDOC_API_Version_1_6_0) return 0;
    *out = &api; return 1;
}
''')
        subprocess.run(["cc", "-shared", "-fPIC", "-I", str(ROOT / "gpu/third_party/renderdoc"),
                        str(cls.path / "api.c"), "-o", str(cls.path / "librenderdoc.so")], check=True)
        (cls.path / "main.c").write_text('#include <unistd.h>\nint main(void) { sleep(2); return 0; }\n')
        subprocess.run(["cc", str(cls.path / "main.c"), "-o", str(cls.path / "bb-probe")], check=True)
        (cls.path / "other-process").write_bytes((cls.path / "bb-probe").read_bytes())
        (cls.path / "other-process").chmod(0o755)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def exercise(self, executable="bb-probe", injected=True):
        with tempfile.TemporaryDirectory(dir=self.path) as folder:
            p = Path(folder)
            trigger = p / "trigger"
            trigger.touch()
            env = os.environ.copy()
            env.update(LD_LIBRARY_PATH=str(self.path),
                       LD_PRELOAD=(str(self.path / "librenderdoc.so") + " " if injected else "") + str(HOOK),
                       SOTC_PIXEL_TRIGGER=str(trigger), SOTC_PIXEL_OUTPUT=str(p / "capture"),
                       TEST_EVENTS=str(p / "events"))
            proc = subprocess.Popen([str(self.path / executable)], env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                if executable == "bb-probe" and injected:
                    deadline = time.monotonic() + 1.5
                    while not (p / "events").exists() and time.monotonic() < deadline:
                        time.sleep(.02)
                    self.assertTrue((p / "events").exists(), "capture API was not called")
                    trigger.touch()  # second trigger must not capture more frames this session
                _, stderr = proc.communicate(timeout=5)
                self.assertEqual(proc.returncode, 0, stderr.decode())
                if executable == "bb-probe" and injected:
                    self.assertEqual((p / "events").read_text(), "3\n")
                    self.assertIn(b"three consecutive presented frames", stderr)
                else:
                    self.assertFalse((p / "events").exists())
                self.assertTrue(trigger.exists())
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.communicate()

    def test_three_frames_once(self):
        self.exercise()

    def test_no_renderdoc_no_capture(self):
        self.exercise(injected=False)

    def test_wrapper_process_is_ignored(self):
        self.exercise(executable="other-process")


if __name__ == "__main__":
    unittest.main()
