# Draws with >= 6 color outputs: event, outputs, VS/PS shader ids, PS texture formats summary.
import os, traceback, collections
import renderdoc as rd
out = open(os.environ["RD_OUT"], "w")
def P(*a):
    out.write(" ".join(str(x) for x in a) + "\n"); out.flush()
def walk(acts, res):
    for a in acts:
        if a.flags & rd.ActionFlags.Drawcall: res.append(a)
        walk(a.children, res)
def main():
    rd.InitialiseReplay(rd.GlobalEnvironment(), [])
    cap = rd.OpenCaptureFile(); cap.OpenFile(os.environ["RD_CAPTURE"], "", None)
    status, ctrl = cap.OpenCapture(rd.ReplayOptions(), None)
    if status != rd.ResultCode.Succeeded:
        P("replay failed", status); return
    tex = {int(t.resourceId): t for t in ctrl.GetTextures()}
    draws = []; walk(ctrl.GetRootActions(), draws)
    cnt = collections.Counter(sum(1 for o in a.outputs if int(o) != 0) for a in draws)
    P("draws", len(draws), "outputs histogram", dict(cnt))
    seen = set()
    for a in draws:
        n = sum(1 for o in a.outputs if int(o) != 0)
        if n < int(os.environ.get("RD_MINOUT", "6")): continue
        ctrl.SetFrameEvent(a.eventId, False)
        st = ctrl.GetPipelineState()
        vs = st.GetShaderReflection(rd.ShaderStage.Vertex); ps = st.GetShaderReflection(rd.ShaderStage.Pixel)
        key = (int(vs.resourceId) if vs else 0, int(ps.resourceId) if ps else 0)
        if key in seen: continue
        seen.add(key)
        def desc(stage):
            l = []
            for r in st.GetReadOnlyResources(stage):
                t = tex.get(int(r.descriptor.resource))
                if t: l.append("%dx%d%s" % (t.width, t.height, t.format.Name()[:6]))
            return l
        P("event", a.eventId, "outs", n, "vs", key[0], "ps", key[1], "VS", desc(rd.ShaderStage.Vertex)[:4], "PS", len(desc(rd.ShaderStage.Pixel)), desc(rd.ShaderStage.Pixel)[:8])
    ctrl.Shutdown(); cap.Shutdown()
try:
    main()
except Exception:
    P(traceback.format_exc())
out.close()
os._exit(0)
