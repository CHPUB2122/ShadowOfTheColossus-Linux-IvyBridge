# Caminho B: otimizações de GPU do bbport no shadPS4 SotC

Pedido original: levar para o nosso shadPS4 as otimizações de GPU do bbport, como o
pipeline de desenho em duas threads e o FSR.

## O que os testes mostraram (07–08/10/2026)

O port nativo rodou primeiro com o núcleo de vídeo do bbport, que traz ~40 otimizações
desligáveis por `BB_TOGGLE_FILE`, listadas em `gpu/shim/bbport_toggles.h` do bbport.

| Otimização do bbport | Efeito no Shadow of the Colossus |
|---|---|
| `PendingFenceWaits` (bit 39) | tela preta intermitente no boot (50–75% das execuções) |
| `DrawPipeline`, `DrawPreparation` e afins (preparo adiantado e diferido) | estado de GPU velho ou lixo durante o streaming ao carregar o save: programas de shader inválidos, `Unpack10_11_11`, device lost |
| leituras de GPU relaxadas (padrão do bbport) | o jogo trava; o SotC precisa de readbacks precisos (`BB_READBACKS=2`) |

Com o núcleo de vídeo do fork no lugar do do bbport (mantendo o carregador e o runtime do
bbport), o jogo ficou correto: menus, save e mundo aberto, 10 min sem queda. Essas
otimizações supõem que o jogo não lê, na CPU, o que a GPU acabou de escrever. Isso vale
para o Bloodborne, mas não para o SotC.

## Medição atual (port nativo, i9-13900K + RTX 2060 SUPER, 1080p)

- Padrão: 30 FPS travado, como no PS4; 22–25 em cargas e no templo.
- Modo `fps60` (vblank 120 Hz): 38 FPS no campo aberto, ~25 no templo.
- Gargalo: a thread `GpuCommandProcessor` fica 72% ocupada. O tempo vai no driver Vulkan e
  em esperas de fence das leituras precisas. Os job workers do jogo ficam em 36–43%.
- O fork no shadPS4 rodava a 17–18 FPS (documento consolidado), então o port nativo já tem
  ~1,7x de desempenho.

## Conclusão

Copiar o pipeline em duas threads do bbport para o fork, como está, quebraria o SotC
pelos motivos da tabela. O FSR não traz ganho porque o jogo já renderiza em 1080p nativo.

O port nativo e o fork agora usam **o mesmo núcleo de vídeo** (os arquivos de
`gpu/shadps4/video_core` são os do fork). Por isso, qualquer otimização feita aqui vale
para os dois. O caminho viável é otimizar esse núcleo comum, uma peça por vez, com teste
A/B: `tools/sotc_hangtest.py` e a rota que carrega o save em `tools/sotc_play.py`.
Candidatos, em ordem de risco:

1. Caches puros do bbport, sem diferimento: `RegionCache`, `FetchShaderCache`,
   `ImageDescCache`, `FindImageCache`, `TextureBindingMemo`, `RenderStateMemo`.
   Atacam o custo da thread de comandos.
2. `ThreadedRecording` (gravação Vulkan noutra thread), mantendo a ordem estrita em relação
   às leituras precisas.
3. Readbacks precisos mais baratos: copiar só as páginas lidas e esperar a fence certa em vez
   de esperar a GPU ociosa.

Cada item é uma fusão manual entre núcleos que divergiram em ~17 mil linhas. O ganho
esperado está no modo 60 FPS: o modo padrão já atinge os 30 do PS4.

## Memória do jogo no lugar: protótipo (08/10/2026)

O bbport original (deadinside28, versão 0.3) tem um "modelo de memória de PC"
(`BB_GUEST_IN_PLACE`): a GPU usa a memória do jogo onde ela está e os rótulos EOP são escritos
quando a GPU realmente terminou. Assim somem as cópias para a VRAM, a proteção de páginas e as
leituras de volta. Medido no Bloodborne: 95 → 115–124 FPS nas cenas pesadas. Lá ele usa dma-buf,
que existe só no Linux e só funciona em AMD.

No Windows o caminho é `VK_EXT_external_memory_host`. O teste `tools/host_import_test.c` mapeia
uma seção do pagefile do mesmo jeito que `src/runtime_memory.c` faz (visão "backing" e visão do
jogo sobre um placeholder) e importa a visão "backing". Resultado na RTX 2060 SUPER:

| Tamanho | Importa | GPU escreve → CPU vê | CPU escreve → GPU lê | GPU lê a memória importada |
|---|---|---|---|---|
| 256 MiB | sim (50 ms) | sim | sim | 5,4 GB/s |
| 2 GiB | sim (460 ms) | sim | sim | 5,7 GB/s |
| 5 GiB | sim (1,5 s) | sim | sim | 5,5 GB/s |

O tipo de memória é host-coherent, sem cache na CPU, e o alinhamento mínimo é 4 KiB. A cópia
VRAM→VRAM foi a 65–184 GB/s. Por isso, texturas e geometria continuam na VRAM; o ganho está nos
dados que a GPU escreve e a CPU lê (o que hoje exige readbacks precisos) e nos rótulos.

**Integração proposta, em etapas mensuráveis:**

1. Importar a visão "backing" inteira na inicialização, como uma `VkDeviceMemory`.
2. Fazer os readbacks copiarem da VRAM direto para a memória do jogo, sem staging e sem memcpy.
   O risco é baixo e o ganho pequeno, mas valida a peça.
3. Mover para a memória importada as regiões que viram "hot readbacks" (as que o jogo relê
   todo quadro). A GPU passa a escrever nelas direto, sem proteção de página nem readback.
4. Rótulos EOP "honestos" (escritos depois da conclusão na GPU) para essas regiões. Com isso a
   sincronização do próprio jogo basta.
