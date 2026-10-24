# Água do SotC no port: o que estava errado e como foi achado

Registro das correções da água (outubro de 2026), para não repetir a investigação.

## Sintomas

- A água ficava lisa, como espelho, sem ondas. Só ondulava muito perto do Wander.
- O lago perto da cascata refletia só objetos próximos. Longe, a superfície ficava escura e lisa.
- Os lagos e rios do mundo aberto, abaixo das cascatas, ficavam totalmente parados.

## Dois tipos de água

1. **Água com simulação** (lago perto da cascata, shader `fs 8356` na captura do lago).
   A CPU atualiza uma textura de simulação de 512×512 em volta do Wander, e o shader de vértices
   tira a normal dela. Fora desse quadrado, as ondas vêm de mapas de normal.
2. **Água com mapa de fluxo** (lagos e rios do mundo aberto, `fs 0xc65f86f1`). Não tem
   simulação: as ondas são mapas de normal BC5 deslocados por um mapa de fluxo e por um relógio
   (`srt[69]`, tempo × velocidade `srt[184]`, com duas fases `fract`).

## Correção 1: DMA ligado por padrão (`294b68e`)

O shader de reflexo em espaço de tela (compute) lê, para cada raio, um registro de *probe* de
224 bytes com índice calculado em tempo de execução. O passo que "achata" as leituras de memória
do shader não consegue resolver esse índice. Sem DMA, a leitura caía em `srt_flatbuf.data[0]`,
então todo pixel usava o mesmo registro.

O Pink-shadPS4 liga `direct_memory_access_enabled` no `CUSA08809.json`. Com DMA, essas leituras
viram acessos diretos à memória do jogo (tabela de páginas BDA). Agora é o padrão do port
(`BB_DIRECT_MEMORY_ACCESS`, em `gpu/shim/core/emulator_settings.h`). Só uns 4 shaders passam a
usar DMA, e o custo medido é desprezível.

## Correção 2: `S_WQM_B64` (`debb0c4`)

No começo do shader da água do mundo aberto:

```
s_mov_b32  vcc_hi, 0x384        ; o jogo usa vcc_hi como registrador comum
...
s_wqm_b64  vcc, exec            ; VCC = máscara de threads ativas (modo "quad inteiro")
...
v_cmp_nle_f32 s[12:13], v9, s87 ; s87 = 0.05
s_and_saveexec_b64 s[88:89], vcc
```

O recompilador tratava `S_WQM_B64` como "não faça nada", o que só é seguro em
`s_wqm_b64 exec, exec`. Aqui o destino é VCC: a metade de baixo de VCC ficava indefinida e a de
cima valia 0x384 (900). Numa GPU NVIDIA (subgrupos de 32), só a metade indefinida conta, então o
ramo que aplica o mapa de fluxo nunca rodava. O shader escrevia sempre a mesma normal, reta para
cima (`0x16ffb801` no G-buffer).

Correção em `shader_recompiler/frontend/translate/scalar_alu.cpp`: quando o destino não é o
EXEC, `S_WQM_B64` grava a máscara expandida para quads inteiros (um quad 2×2 com qualquer bit
ligado fica com os quatro) e define o SCC. O Pink tem o mesmo problema.

- A primeira versão só copiava a máscara. A água ficou certa, mas as copas das árvores distantes
  ganharam "lixo colorido". A folhagem usa `s_wqm_b64` no teste de transparência para manter
  vivos os vizinhos do quad, de que a GPU precisa para calcular o nível de detalhe da textura.
  Sem a expansão, ela lia mips com lixo.
- A expansão é feita por thread (cada pixel junta os 4 bits do seu quad com `QuadBroadcast` e
  depois `Ballot`), não com deslocamentos na máscara de 64 bits. O passo de eliminação de
  `InverseBallot` trata máscaras como um booleano por thread e aborta com uma constante como
  `0x1111111111111111`.
- Só 9 pixel shaders do jogo usam essa forma (`s_wqm_b64 vcc, exec` ou `vcc, vcc`).
  `SOTC_WQM_COPY=0` volta ao comportamento antigo, para comparação.

## Método (scripts em `tools/rdoc`; rodar com `qrenderdoc.exe --python <script>` e as variáveis `RD_*`)

1. **Captura no RenderDoc:** `SOTC_WRAP` (JSON com `renderdoccmd capture`) +
   `SOTC_RDOC_SUBMITS=8` + `SOTC_RECORD_THREAD=0`, e F12 no jogo. Abrir a captura exige o jogo
   fechado, porque não sobra VRAM. O primeiro quadro tem argumentos indiretos com lixo; use os
   quadros seguintes.
2. **Achar o draw:** listar os draws por shader e texturas (`rd_findps.py`). O histórico de
   pixel do G-buffer (`rd_hist.py`) mostra qual draw escreveu cada pixel.
3. **Conferir as entradas:** views e mips (`rd_views.py`, `rd_mipsminmax.py`), constantes
   (`rd_flatdump.py`), buffers de vértice (`rd_vsbufs.py`) e saídas (`rd_raw.py`, que salva os
   bytes do G-buffer para decodificar em Python).
4. **Instrumentar o shader:** extrair o SPIR-V (`rd_spv.py`), desmontar com `spirv-dis`, trocar
   o que vai para `frag_color0` por valores intermediários (`spv_probe.py`), montar com
   `spirv-as`, substituir na captura (`BuildTargetShader` + `ReplaceResource`) e ler o pixel
   (`rd_probe.py`). Foi assim que apareceu a normal reta e o ramo com `InverseBallot` sobre
   `(Undef, 900)`.
5. **Ver o código GCN:** `BB_DUMP_SHADERS=1` grava o IR e o binário de cada shader compilado em
   `user/shader/dumps`. O `tools/rdoc/gcnscan.py` é um decodificador GCN mínimo que marca as
   instruções que tocam VCC.
