# Save every color output of RD_EVENT as PNG (and depth), range RD_WHITE.
import os, traceback
import renderdoc as rd
out = open(os.environ["RD_OUT"], "w")
def P(*a):
    out.write(" ".join(str(x) for x in a) + "\n"); out.flush()
def main():
    rd.InitialiseReplay(rd.GlobalEnvironment(), [])
    cap = rd.OpenCaptureFile(); cap.OpenFile(os.environ["RD_CAPTURE"], "", None)
    status, ctrl = cap.OpenCapture(rd.ReplayOptions(), None)
    if status != rd.ResultCode.Succeeded:
        P("replay failed", status); return
    ctrl.SetFrameEvent(int(os.environ["RD_EVENT"]), True)
    st = ctrl.GetPipelineState()
    tex = {int(t.resourceId): t for t in ctrl.GetTextures()}
    for i, o in enumerate(st.GetOutputTargets()):
        rid = int(o.resource)
        if rid == 0: continue
        t = tex[rid]
        mn, mx = ctrl.GetMinMax(o.resource, rd.Subresource(0, 0, 0), rd.CompType.Typeless)
        P("out", i, rid, t.width, t.height, t.format.Name(), "min", [round(v,3) for v in mn.floatValue], "max", [round(v,3) for v in mx.floatValue])
        s = rd.TextureSave(); s.resourceId = o.resource; s.destType = rd.FileType.PNG
        s.alpha = rd.AlphaMapping.Discard
        s.comp.blackPoint = 0.0; s.comp.whitePoint = float(os.environ.get("RD_WHITE", "1"))
        ctrl.SaveTexture(s, os.path.join(os.environ["RD_DIR"], "out%d_%d.png" % (i, rid)))
    ctrl.Shutdown(); cap.Shutdown()
try:
    main()
except Exception:
    P(traceback.format_exc())
out.close()
os._exit(0)
