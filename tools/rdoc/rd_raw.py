# Raw mip-0 bytes of the color outputs RD_SLOTS at RD_EVENT -> RD_DIR/raw_<slot>.bin
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
    outs = ctrl.GetPipelineState().GetOutputTargets()
    for s in [int(x) for x in os.environ["RD_SLOTS"].split(",")]:
        data = ctrl.GetTextureData(outs[s].resource, rd.Subresource(0, 0, 0))
        open(os.path.join(os.environ["RD_DIR"], "raw_%d.bin" % s), "wb").write(bytes(data))
        P("slot", s, len(data))
    ctrl.Shutdown(); cap.Shutdown()
try: main()
except Exception: P(traceback.format_exc())
out.close(); os._exit(0)
