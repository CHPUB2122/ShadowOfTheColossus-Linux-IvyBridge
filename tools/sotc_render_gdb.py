"""sotc: loaded by GDB through sotc_render_debug.py; never modifies guest state."""
import collections
import json
import math
import os
import struct
import gdb

counts = collections.Counter()
thread_counts = collections.Counter()
stop_signal = None


def stopped(event):
    global stop_signal
    if isinstance(event, gdb.SignalEvent):
        stop_signal = event.stop_signal


gdb.events.stop.connect(stopped)


def emit(message):
    gdb.write("RENDER-DIAG " + message + "\n")


class Boundary(gdb.Breakpoint):
    def __init__(self, name, symbol):
        super().__init__(symbol, internal=True)
        self.name = name
        self.silent = True
        counts[name] = 0

    def stop(self):
        counts[self.name] += 1
        n = counts[self.name]
        thread = gdb.selected_thread()
        thread_counts[f"{self.name}:{thread.ptid[1]}:{thread.name}"] += 1
        if self.name == "event_trigger_attempt":
            ident = int(gdb.parse_and_eval("$rsi"))
            event_filter = int(gdb.parse_and_eval("(short)$rdx"))
            counts[f"event_{ident:#x}_filter_{event_filter}_attempt"] += 1
        if n <= 3 or n & (n - 1) == 0:
            emit(f"{self.name}={n} thread={thread.name} tid={thread.ptid[1]}")
        return False


def memory(address, size):
    return bytes(gdb.selected_inferior().read_memory(address, size))


def u64(address):
    return struct.unpack("<Q", memory(address, 8))[0]


def f32(address):
    return struct.unpack("<f", memory(address, 4))[0]


def timer_snapshot(base):
    # This is a read-only diagnosis of the exact loop seen in six existing logs.
    # Refuse the offsets if the prepared executable has different instructions.
    if memory(base + 0x25cdb0, 14) != bytes.fromhex("c5e25cdcc5da58d2c5f82edc73f2"):
        emit("timer signature differs; skipping version-specific reads")
        return
    for thread in gdb.selected_inferior().threads():
        thread.switch()
        pc = int(gdb.parse_and_eval("$pc")) - base
        if not 0x25ccc0 <= pc < 0x25ce80:
            continue
        emit(f"timer thread={thread.name} tid={thread.ptid[1]} offset={pc:#x}")
        gdb.execute("info registers rax rbx rcx rdx rdi rsi rbp rsp eflags xmm0 xmm1 xmm2 xmm3 xmm4 xmm5 xmm6 mxcsr")
        obj = int(gdb.parse_and_eval("$rbx"))
        raw = memory(obj, 0x48)
        emit(f"timer object={obj:#x} bytes={raw.hex()}")
        emit(f"timer tsc_origin={u64(obj + 0x10)} previous_seconds={struct.unpack_from('<d', raw, 0x18)[0]!r}")
        emit(f"timer fields_28_2c_30={struct.unpack_from('<3f', raw, 0x28)!r}")
        emit(f"timer tsc_frequency={u64(base + 0x2ea4700)} target_dt={f32(base + 0x2eee7b0)!r}")
        step_ptr = u64(base + 0x2eecde8 + 0x60)
        emit(f"timer step_scale_ptr={step_ptr:#x} step_scale={f32(step_ptr)!r}")
        a = float(gdb.parse_and_eval("$xmm3.v4_float[0]"))
        b = float(gdb.parse_and_eval("$xmm4.v4_float[0]"))
        after = struct.unpack("<f", struct.pack("<f", a - b))[0]
        emit(f"timer subtract float32: {a!r} - {b!r} = {after!r}; unchanged={a == after}; finite={math.isfinite(a) and math.isfinite(b)}")


for command in (
    "set pagination off", "set confirm off", "set breakpoint pending on",
    "set debuginfod enabled off", "set print elements 24", "set disable-randomization off",
    "set print thread-events off",
    "handle SIGILL nostop noprint pass", "handle SIGSEGV nostop noprint pass",
    "handle SIGUSR2 nostop noprint pass", "handle SIGALRM stop print nopass",
):
    gdb.execute(command)

boundaries = (
    ("gnm_submit", "Libraries::GnmDriver::sceGnmSubmitCommandBuffersForWorkload"),
    ("gnm_submit_flip", "Libraries::GnmDriver::sceGnmSubmitAndFlipCommandBuffersForWorkload"),
    ("gnm_done", "Libraries::GnmDriver::sceGnmSubmitDone"),
    ("gfx_queued", "AmdGpu::Liverpool::SubmitGfx"),
    ("gfx_started", "gpu/shadps4/video_core/amdgpu/liverpool.cpp:704"),
    ("vulkan_draw", "Vulkan::Rasterizer::Draw"),
    ("vulkan_submit", "Vulkan::Scheduler::SubmitExecution"),
    ("flip_request", "Libraries::VideoOut::VideoOutDriver::SubmitFlip"),
    ("flip_dequeued", "Libraries::VideoOut::VideoOutDriver::Flip"),
    ("present_call", "Vulkan::Presenter::Present"),
    ("swapchain_present_call", "Vulkan::Swapchain::Present"),
    ("event_trigger_attempt", "Libraries::Kernel::EqueueInternal::TriggerEvent"),
)

try:
    # Stop at main after the shared library has loaded: resolve breakpoints
    # against its real symbols and keep the exec/linker SIGTRAP inside GDB.
    gdb.execute("start")
    gdb.execute("handle SIGTRAP nostop noprint pass")
    if os.environ.get("SOTC_GDB_BOUNDARIES") == "1":
        for name, symbol in boundaries:
            Boundary(name, symbol)
    else:
        emit("using compiled counters; per-draw breakpoints disabled to preserve timing")
    gdb.execute("continue")
    emit("boundary counts=" + json.dumps(dict(counts), sort_keys=True))
    emit("boundary threads=" + json.dumps(dict(thread_counts), sort_keys=True))
    if gdb.selected_inferior().pid:
        gdb.execute("info sharedlibrary")
        gdb.execute("info threads")
        gdb.execute("thread apply all bt full 16")
        base = int(gdb.parse_and_eval("image"))
        emit(f"guest image base={base:#x}")
        try:
            timer_snapshot(base)
        except (gdb.error, ValueError, OverflowError, struct.error) as error:
            emit(f"timer snapshot incomplete: {error}")
        # These values distinguish command processing backlog from an idle GPU.
        for expression in ("liverpool->num_submits", "liverpool->num_commands",
                           "liverpool->num_ordered", "liverpool->back_head", "liverpool->back_tail",
                           "liverpool->vo_port->flip_status"):
            try:
                gdb.execute("print " + expression)
            except gdb.error as error:
                emit(f"cannot read {expression}: {error}")
        # Preserve the actual stop reason; do not turn a different fault into a timeout.
        if stop_signal:
            emit(f"resuming original stop signal: {stop_signal}")
            gdb.execute(f"handle {stop_signal} nostop noprint pass")
            gdb.execute("signal " + stop_signal)
        else:
            gdb.execute("continue")
    else:
        emit("inferior exited before watchdog; inspect initialization/fault messages above")
    try:
        code = int(gdb.parse_and_eval("$_exitcode"))
    except (gdb.error, TypeError):
        code = 1
    gdb.execute(f"quit {code}")
except gdb.error as error:
    emit(f"GDB failed: {error}")
    gdb.execute("quit 1")
