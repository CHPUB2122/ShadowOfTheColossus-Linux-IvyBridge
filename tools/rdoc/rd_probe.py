# Replace the PS of RD_EVENT by each SPIR-V in RD_SPVS (comma list) and read RT0 at RD_PIX (x:y;...).
import os, traceback
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
    orig = st.GetShader(rd.ShaderStage.Pixel)
    rt = st.GetOutputTargets()[0].resource
    pix = [tuple(int(v) for v in p.split(":")) for p in os.environ["RD_PIX"].split(";")]
    for spv in os.environ["RD_SPVS"].split(","):
        data = open(spv, "rb").read()
        new, err = ctrl.BuildTargetShader("main", rd.ShaderEncoding.SPIRV, data, rd.ShaderCompileFlags(), rd.ShaderStage.Pixel)
        if err: P("build", spv, err)
        ctrl.ReplaceResource(orig, new)
        ctrl.SetFrameEvent(ev, True)
        for x, y in pix:
            v = ctrl.PickPixel(rt, x, y, rd.Subresource(0, 0, 0), rd.CompType.Typeless)
            P(os.path.basename(spv), x, y, ["%.5g" % f for f in v.floatValue[:4]])
        ctrl.RemoveReplacement(orig)
        ctrl.FreeTargetResource(new)
    ctrl.Shutdown(); cap.Shutdown()
try: main()
except Exception: P(traceback.format_exc())
out.close(); os._exit(0)
