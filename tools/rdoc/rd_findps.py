# Draws (any outputs) whose PS reads >= RD_MINTEX textures; dedup by shader pair. Also presents.
import os, traceback
import renderdoc as rd
out = open(os.environ["RD_OUT"], "w")
def P(*a):
    out.write(" ".join(str(x) for x in a) + "\n"); out.flush()
def walk(acts, res):
    for a in acts:
        res.append(a); walk(a.children, res)
def main():
    rd.InitialiseReplay(rd.GlobalEnvironment(), [])
    cap = rd.OpenCaptureFile(); cap.OpenFile(os.environ["RD_CAPTURE"], "", None)
    status, ctrl = cap.OpenCapture(rd.ReplayOptions(), None)
    sf = ctrl.GetStructuredFile()
    tex = {int(t.resourceId): t for t in ctrl.GetTextures()}
    acts = []; walk(ctrl.GetRootActions(), acts)
    seen = set()
    for a in acts:
        nm = a.GetName(sf)
        if "Present" in nm: P("PRESENT", a.eventId); continue
        if not (a.flags & rd.ActionFlags.Drawcall): continue
        ctrl.SetFrameEvent(a.eventId, False)
        st = ctrl.GetPipelineState()
        vs = st.GetShaderReflection(rd.ShaderStage.Vertex); ps = st.GetShaderReflection(rd.ShaderStage.Pixel)
        key = (int(vs.resourceId) if vs else 0, int(ps.resourceId) if ps else 0)
        if key in seen: continue
        seen.add(key)
        l = []
        for r in st.GetReadOnlyResources(rd.ShaderStage.Pixel):
            t = tex.get(int(r.descriptor.resource))
            if t: l.append("%dx%d%s" % (t.width, t.height, t.format.Name()[:6]))
        if len(l) >= int(os.environ.get("RD_MINTEX", "15")):
            n = sum(1 for o in a.outputs if int(o) != 0)
            P("event", a.eventId, "outs", n, "vs", key[0], "ps", key[1], len(l), l)
    ctrl.Shutdown(); cap.Shutdown()
try: main()
except Exception: P(traceback.format_exc())
out.close(); os._exit(0)
