# Pixel history of output slot RD_SLOT texture at (RD_X,RD_Y) up to RD_EVENT.
import os, traceback
import renderdoc as rd
out = open(os.environ["RD_OUT"], "w")
def P(*a):
    out.write(" ".join(str(x) for x in a) + "\n"); out.flush()
def main():
    rd.InitialiseReplay(rd.GlobalEnvironment(), [])
    cap = rd.OpenCaptureFile(); cap.OpenFile(os.environ["RD_CAPTURE"], "", None)
    status, ctrl = cap.OpenCapture(rd.ReplayOptions(), None)
    sf = ctrl.GetStructuredFile()
    ctrl.SetFrameEvent(int(os.environ["RD_EVENT"]), True)
    st = ctrl.GetPipelineState()
    res = st.GetOutputTargets()[int(os.environ["RD_SLOT"])].resource
    lo = int(os.environ.get("RD_FROM", "0"))
    hist = ctrl.PixelHistory(res, int(os.environ["RD_X"]), int(os.environ["RD_Y"]), rd.Subresource(0,0,0), rd.CompType.Typeless)
    for h in hist:
        if h.eventId < lo: continue
        a = None
        ctrl.SetFrameEvent(h.eventId, False)
        s2 = ctrl.GetPipelineState()
        P("ev", h.eventId, a.GetName(sf) if a else "?", "vs", int(s2.GetShader(rd.ShaderStage.Vertex)), "ps", int(s2.GetShader(rd.ShaderStage.Pixel)),
          "pre", [hex(x) for x in h.preMod.col.uintValue[:1]], "post", [hex(x) for x in h.postMod.col.uintValue[:1]], "passed", h.Passed())
    ctrl.Shutdown(); cap.Shutdown()
try: main()
except Exception: P(traceback.format_exc())
out.close(); os._exit(0)
