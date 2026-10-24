# Dump dwords 0..RD_N of the PS srt_flatbuf at RD_EVENT.
import os, traceback, struct
import renderdoc as rd
out = open(os.environ["RD_OUT"], "w")
def P(*a):
    out.write(" ".join(str(x) for x in a) + "\n"); out.flush()
def main():
    rd.InitialiseReplay(rd.GlobalEnvironment(), [])
    cap = rd.OpenCaptureFile(); cap.OpenFile(os.environ["RD_CAPTURE"], "", None)
    status, ctrl = cap.OpenCapture(rd.ReplayOptions(), None)
    ctrl.SetFrameEvent(int(os.environ["RD_EVENT"]), True)
    st = ctrl.GetPipelineState()
    stg = rd.ShaderStage.Pixel if not os.environ.get("RD_VS") else rd.ShaderStage.Vertex
    refl = st.GetShaderReflection(stg)
    n = int(os.environ.get("RD_N", "400"))
    for u in st.GetReadWriteResources(stg):
        idx = u.access.index
        if idx < len(refl.readWriteResources) and "flat" in refl.readWriteResources[idx].name:
            d = u.descriptor
            data = ctrl.GetBufferData(d.resource, d.byteOffset, n*4)
            for k in range(len(data)//4):
                w = struct.unpack_from("<I", data, k*4)[0]; f = struct.unpack_from("<f", data, k*4)[0]
                P(k, "%08x" % w, "%g" % f)
    ctrl.Shutdown(); cap.Shutdown()
try: main()
except Exception: P(traceback.format_exc())
out.close(); os._exit(0)
