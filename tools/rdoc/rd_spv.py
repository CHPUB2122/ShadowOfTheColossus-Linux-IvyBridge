# Save raw SPIR-V of the VS and PS of RD_EVENT to RD_DIR/{vs,ps}.spv
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
    for nm, stg in (("vs", rd.ShaderStage.Vertex), ("ps", rd.ShaderStage.Pixel)):
        r = st.GetShaderReflection(stg)
        open(os.path.join(os.environ["RD_DIR"], nm + ".spv"), "wb").write(bytes(r.rawBytes))
        P(nm, int(r.resourceId), r.encoding, len(r.rawBytes), r.entryPoint)
    ctrl.Shutdown(); cap.Shutdown()
try: main()
except Exception: P(traceback.format_exc())
out.close(); os._exit(0)
