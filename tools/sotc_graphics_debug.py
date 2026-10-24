#!/usr/bin/env python3
"""Isolated engine effect profiles and read-only CVar sampling (SotC EU 1.01)."""
import os
import re
import struct


PROFILES = {
    "baseline": {},
    "motion-off": {"r_motionBlurEnable": "0"},
    # Method 0 gates history use at guest +0xb6a49. The engine still resolves
    # current colour; do not skip Vulkan dispatches or leave outputs unwritten.
    "temporal-off": {"r_aaMethod": "0", "r_aaEnableTemporalProjectMatrixJitter": "0",
                     "r_aaEnableTemporalDitherBuffer": "0"},
    "bloom-off": {"r_bloomEnable": "0", "r_bloomEnableFakeBloom": "0"},
    "subsurface-off": {"r_subsurfaceScale": "0"},
}
PROFILES["post-off"] = {k: v for name in ("motion-off", "temporal-off", "bloom-off")
                        for k, v in PROFILES[name].items()}

# CVar object, constructor LEA, string offset, type. These are checked against
# the prepared image before the new profile is written. No original game write.
CVARS = {
    "r_motionBlurEnable": (0x2eb9fa8, 0x83bc4, 0xf9c3b5, "B"),
    "r_aaMethod": (0x2eba478, 0x84206, 0xf9c44f, "i"),
    "r_aaEnableTemporalProjectMatrixJitter": (0x2eba618, 0x8440a, 0xf9c473, "B"),
    "r_aaEnableTemporalDitherBuffer": (0x2eba6d8, 0x844f6, 0xf9c499, "B"),
    "r_bloomEnable": (0x2eb8098, 0x81430, 0xf9c09d, "B"),
    "r_bloomEnableFakeBloom": (0x2eb8218, 0x8160c, 0xf9c0c0, "B"),
    "r_subsurfaceScale": (0x2eb03d0, 0x772f6, 0xf9b407, "f"),
}
CMDLINE_SITE = 0x5367b9
CMDLINE_BYTES = bytes.fromhex("488d352debad00")


def validate_image(image):
    if image[CMDLINE_SITE:CMDLINE_SITE + 7] != CMDLINE_BYTES:
        raise ValueError("prepared image is not the supported EU 1.01 command-line site")
    for name, (obj, site, text, kind) in CVARS.items():
        opcode = b"\x4c\x8d\x2d" if name == "r_subsurfaceScale" else b"\x48\x8d\x1d"
        expected = opcode + struct.pack("<i", obj - site - 7)
        label = name.encode() + b"\0"
        if image[site:site + 7] != expected or image[text:text + len(label)] != label:
            raise ValueError(f"unsupported CVar layout: {name}")


def validate_prepared(boot_path):
    boot = boot_path.read_bytes()
    if len(boot) < 16 or boot[:8] != b"BBPROBE5":
        raise ValueError("graphics profiles require an existing BBPROBE5 image")
    size = struct.unpack_from("<Q", boot, 8)[0]
    if not 0 < size <= len(boot) - 16:
        raise ValueError("invalid prepared image size")
    validate_image(boot[-size:])


def make_profile(boot_path, cmdline_path, output, profile):
    validate_prepared(boot_path)
    data = cmdline_path.read_bytes()
    if len(data) < 16 or struct.unpack_from("<8sQ", data) != (b"SOTCCMD1", CMDLINE_SITE):
        raise ValueError("unsupported existing SOTCCMD1 file")
    text = data[16:].decode("ascii")
    tokens = text.split()
    if not tokens or any(not re.fullmatch(r"\+[A-Za-z_][A-Za-z0-9_]*(=[-+.0-9A-Za-z_%]+)?", t)
                         for t in tokens):
        raise ValueError("unexpected existing engine command line")
    settings = PROFILES[profile]
    # Replace only this profile's controls, retaining all unrelated existing CVars.
    tokens = [t for t in tokens if t[1:].split("=", 1)[0] not in settings]
    tokens += [f"+{k}={v}" for k, v in settings.items()]
    with output.open("xb") as target:
        target.write(data[:16] + " ".join(tokens).encode("ascii"))
    return {"name": profile, "requested": settings, "command_line": " ".join(tokens),
            "cmdline_file": str(output), "layout": "CUSA08809 EU 1.01",
            "note": "Velocity production and final composition are retained. Samples verify settings after menu load."}


def check_profile(profile, samples):
    if not profile:
        return {"status": "not-requested"}
    expected = profile["requested"]
    if not expected:
        return {"status": "baseline", "requested": {}}
    ready = [s for s in samples if s.get("status") == "ok"]
    if not ready:
        return {"status": "unconfirmed", "requested": expected}
    last = ready[-1]
    mismatches = {k: last["values"].get(k) for k, v in expected.items()
                  if last["values"].get(k) != float(v)}
    return {"status": "mismatch" if mismatches else "observed",
            "sample_seconds": last["seconds"], "requested": expected,
            "mismatches": mismatches,
            "note": "Observed CVar source values; not proof of visual correctness or frame-copy contents."}


def sample_cvars(pid, game_log):
    """Parent reads child memory only; unavailable permissions are reported explicitly."""
    match = re.search(rb"Image at (0x[0-9a-f]+) \(below 2 GiB\)", game_log)
    if not match:
        return {"status": "image-not-loaded"}
    base = int(match[1], 16)
    try:
        fd = os.open(f"/proc/{pid}/mem", os.O_RDONLY)
        try:
            # Check relocated process bytes too, before touching known CVar slots.
            if os.pread(fd, 7, base + 0x83bc4) != b"\x48\x8d\x1d" + struct.pack("<i", 0x2eb9fa8 - 0x83bc4 - 7):
                return {"status": "unsupported-process-layout"}
            values = {}
            for name, (obj, site, text, kind) in CVARS.items():
                data = os.pread(fd, 8, base + obj + 0x60)
                ptr = struct.unpack("<Q", data)[0]
                # All backing values belong to this image's settings structure.
                if not base + 0x2ea8ee8 <= ptr < base + 0x2ea99b0:
                    values[name] = {"status": "not-initialized", "pointer": hex(ptr)}
                    continue
                value = struct.unpack("<" + kind, os.pread(fd, struct.calcsize(kind), ptr))[0]
                values[name] = value
            return {"status": "ok", "image_base": hex(base), "values": values}
        finally:
            os.close(fd)
    except (OSError, struct.error) as error:
        return {"status": "unavailable", "reason": str(error)}
