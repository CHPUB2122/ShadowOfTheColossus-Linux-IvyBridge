# VS read-write buffers at RD_EVENT: name, resource, offset, size, first RD_N dwords; and who wrote it (usage).
import os, traceback, struct
import renderdoc as rd
out = open(os.environ["RD_OUT"], "w")
def P(*a):
    out.write(" ".join(str(x) for x in a) + "\n"); out.flush()
def main():
    rd.InitialiseReplay(rd.GlobalEnvironment(), [])
    cap = rd.OpenCaptureFile(); cap.OpenFile(os.environ["RD_CAPTURE"], "", None)
    status, ctrl = cap.OpenCapture(rd.ReplayOptions(), None)
    ev = int(os.environ["RD_EVENT"])
    ctrl.SetFrameEvent(ev, True)
    st = ctrl.GetPipelineState()
    refl = st.GetShaderReflection(rd.ShaderStage.Vertex)
    n = int(os.environ.get("RD_N", "16"))
    for u in st.GetReadWriteResources(rd.ShaderStage.Vertex):
        idx = u.access.index
        name = refl.readWriteResources[idx].name if idx < len(refl.readWriteResources) else "?"
        d = u.descriptor
        if int(d.resource) == 0: continue
        data = ctrl.GetBufferData(d.resource, d.byteOffset, n*4)
        P(name, int(d.resource), "off", d.byteOffset, "size", d.byteSize, " ".join("%08x" % struct.unpack_from("<I", data, k*4)[0] for k in range(len(data)//4)))
        if name in os.environ.get("RD_USAGE", "").split(","):
            us = [x for x in ctrl.GetUsage(d.resource) if x.eventId < ev]
            P("  writers:", [(x.eventId, str(x.usage).split('.')[-1]) for x in us if "Write" in str(x.usage) or "Copy" in str(x.usage) or "Clear" in str(x.usage)][-10:])
    ctrl.Shutdown(); cap.Shutdown()
try: main()
except Exception: P(traceback.format_exc())
out.close(); os._exit(0)
