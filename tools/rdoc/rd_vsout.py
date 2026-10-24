# All post-VS output floats for the first RD_N vertices of RD_EVENT, plus NaN/zero stats per float column.
import os, struct, traceback, math
import renderdoc as rd
out = open(os.environ["RD_OUT"], "w")
def P(*a):
    out.write(" ".join(str(x) for x in a) + "\n"); out.flush()
def main():
    rd.InitialiseReplay(rd.GlobalEnvironment(), [])
    cap = rd.OpenCaptureFile(); cap.OpenFile(os.environ["RD_CAPTURE"], "", None)
    status, ctrl = cap.OpenCapture(rd.ReplayOptions(), None)
    ctrl.SetFrameEvent(int(os.environ["RD_EVENT"]), True)
    refl = ctrl.GetPipelineState().GetShaderReflection(rd.ShaderStage.Vertex)
    for s in refl.outputSignature: P("out sig", s.varName, s.semanticName, s.regIndex, s.compCount)
    mesh = ctrl.GetPostVSData(0, 0, rd.MeshDataStage.VSOut)
    data = ctrl.GetBufferData(mesh.vertexResourceId, 0, 0)
    stride = mesh.vertexByteStride; nf = stride // 4
    count = len(data) // stride
    P("stride", stride, "count", count, "posOffset", mesh.vertexByteOffset)
    n = int(os.environ.get("RD_N", "6"))
    cols = [[] for _ in range(nf)]
    for i in range(count):
        v = struct.unpack_from("%df" % nf, data, i * stride)
        for k in range(nf): cols[k].append(v[k])
        if i < n: P(i, " ".join("%.4g" % x for x in v))
    for k in range(nf):
        c = cols[k]; nan = sum(1 for x in c if x != x); fin = [x for x in c if x == x and abs(x) != math.inf]
        P("col", k, "nan", nan, "inf", sum(1 for x in c if abs(x) == math.inf), "min %.4g max %.4g" % (min(fin), max(fin)) if fin else "")
    ctrl.Shutdown(); cap.Shutdown()
try: main()
except Exception: P(traceback.format_exc())
out.close(); os._exit(0)
