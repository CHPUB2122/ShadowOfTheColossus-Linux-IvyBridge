# Image view mip range and sampler LOD range for every PS read-only binding at RD_EVENT.
import os, traceback
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
    for stg in (rd.ShaderStage.Vertex, rd.ShaderStage.Pixel):
        P("==", stg)
        for u in st.GetReadOnlyResources(stg):
            d = u.descriptor
            P("bind", u.access.index, int(d.resource), "firstMip", d.firstMip, "numMips", d.numMips, "minLODClamp", getattr(d, "minLODClamp", "?"))
        for s in st.GetSamplers(stg):
            sd = s.sampler
            P("samp", s.access.index, "minLOD", sd.minLOD, "maxLOD", sd.maxLOD, "bias", sd.mipBias, "filter", sd.filter.mip, "aniso", sd.maxAnisotropy)
    ctrl.Shutdown(); cap.Shutdown()
try: main()
except Exception: P(traceback.format_exc())
out.close(); os._exit(0)
