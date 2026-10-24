# Min/max of every mip of RD_IDS at event RD_EVENT, and PNGs of the mips (scaled to RD_WHITE).
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
    tex = {int(t.resourceId): t for t in ctrl.GetTextures()}
    for i in [int(v) for v in os.environ["RD_IDS"].split(",")]:
        t = tex[i]
        for m in range(t.mips):
            mn, mx = ctrl.GetMinMax(t.resourceId, rd.Subresource(m, 0, 0), rd.CompType.Typeless)
            P(i, "mip", m, "min %.3f max %.3f" % (mn.floatValue[0], mx.floatValue[0]))
            s = rd.TextureSave(); s.resourceId = t.resourceId; s.destType = rd.FileType.PNG
            s.mip = m; s.alpha = rd.AlphaMapping.Discard
            s.comp.blackPoint = 0.0; s.comp.whitePoint = float(os.environ.get("RD_WHITE", "100"))
            ctrl.SaveTexture(s, os.path.join(os.environ["RD_DIR"], "t%d_m%d.png" % (i, m)))
    ctrl.Shutdown(); cap.Shutdown()
try:
    main()
except Exception:
    P(traceback.format_exc())
out.close()
os._exit(0)
