# Everything one draw reads: textures (saved as PNG, with min/max), samplers count, buffers,
# vertex/pixel shader disassembly. Env: RD_CAPTURE, RD_OUT, RD_EVENT, RD_DIR.
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
    tex = {int(t.resourceId): t for t in ctrl.GetTextures()}
    bufs = {int(b.resourceId): b for b in ctrl.GetBuffers()}
    ev = int(os.environ["RD_EVENT"]); d = os.environ["RD_DIR"]
    ctrl.SetFrameEvent(ev, True)
    st = ctrl.GetPipelineState()
    for stg in ((rd.ShaderStage.Compute,) if os.environ.get("RD_CS") else (rd.ShaderStage.Vertex, rd.ShaderStage.Pixel)):
        P("== stage", stg, "shader", int(st.GetShader(stg)))
        for i, u in enumerate(st.GetReadOnlyResources(stg)):
            r = int(u.descriptor.resource)
            if r in tex:
                t = tex[r]
                mm = ctrl.GetMinMax(t.resourceId, rd.Subresource(0, 0, 0), rd.CompType.Typeless)
                P("tex", i, "bind", u.access.index, r, "%dx%dx%d mips=%d arr=%d" % (t.width, t.height, t.depth, t.mips, t.arraysize),
                  t.format.Name(), "min", ["%.3f" % v for v in mm[0].floatValue[:4]], "max", ["%.3f" % v for v in mm[1].floatValue[:4]])
                if t.width >= 8 and t.depth == 1 and t.arraysize == 1:
                    s = rd.TextureSave(); s.resourceId = t.resourceId; s.destType = rd.FileType.PNG
                    s.alpha = rd.AlphaMapping.Discard
                    ctrl.SaveTexture(s, os.path.join(d, "e%d_%s_%d_%d.png" % (ev, ("cs" if stg == rd.ShaderStage.Compute else "vs" if stg == rd.ShaderStage.Vertex else "ps"), i, r)))
            elif r in bufs:
                P("buf", i, r, bufs[r].length)
            else:
                P("res", i, r)
        for i, u in enumerate(st.GetReadWriteResources(stg)):
            P("rw", i, int(u.descriptor.resource))
        refl = st.GetShaderReflection(stg)
        if refl:
            targets = ctrl.GetDisassemblyTargets(True)
            dis = ctrl.DisassembleShader(st.GetComputePipelineObject() if stg == rd.ShaderStage.Compute else st.GetGraphicsPipelineObject(), refl, targets[0])
            open(os.path.join(d, "e%d_%s.txt" % (ev, ("cs" if stg == rd.ShaderStage.Compute else "vs" if stg == rd.ShaderStage.Vertex else "ps"))), "w").write(dis)
    ctrl.Shutdown(); cap.Shutdown()
try:
    main()
except Exception:
    P(traceback.format_exc())
out.close()
os._exit(0)
