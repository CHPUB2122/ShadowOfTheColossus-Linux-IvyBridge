# Shadow of the Colossus PC — revisão completa do projeto

Estado em 12/10/2026 (ramo `sotc`, commit `e5d6233` e seguintes). Repositório público:
<https://github.com/AjncSystem/ShadowOfTheColossus-PC> (versões 0.0.8 e 0.0.9 publicadas).

Este documento junta, num lugar só, o que o projeto é, como funciona, tudo o que foi feito
até agora, os números de desempenho, os problemas conhecidos e os próximos passos.

---

## 1. O que é

Um **port nativo para Windows** do *Shadow of the Colossus* de PS4 (CUSA08809, EU, versão
1.01 do executável). Não é um emulador completo como o shadPS4: o código do jogo roda
**direto no processador do PC**, e só o que é exclusivo do PS4 é recriado:

| Parte do PS4 | Como o port resolve |
|---|---|
| CPU (AMD Jaguar, x86-64) | o código do jogo roda **nativo** no x86-64 do PC (mesma arquitetura). Só as poucas instruções que o Intel não tem (SSE4a) e o uso da *red zone* são corrigidos no carregamento. |
| Sistema operacional (Orbis OS) | um runtime próprio (`src/runtime_*.c`) implementa as funções do sistema que o jogo chama: memória, arquivos, threads, saves, áudio, controle, diálogos… |
| GPU (AMD GCN "Liverpool") | **emulada**: os comandos PM4 e os shaders GCN do jogo são traduzidos para **Vulkan** (núcleo de vídeo do shadPS4, com as correções do nosso fork). |
| Bibliotecas do jogo (libc, Fios) | as do próprio dump são ligadas nativamente na preparação. |
| Som (libSceNgs2 / libSceUlt) | os módulos **do console do próprio usuário** são ligados (nunca distribuídos). |

Base: o projeto *bbport* (port nativo de Bloodborne, GPL-2.0), adaptado ao SotC.

## 2. Como funciona (fluxo de execução)

1. **`SotC.exe`** (lançador, Python/Tkinter congelado com PyInstaller): primeira configuração,
   biblioteca de jogos, opções de imagem/controles, e então chama o `sotc.py`.
2. **`sotc.py`**: prepara o jogo uma vez (e de novo só quando algo muda):
   - `scripts/prepare.py` transforma o `eboot.bin` (SELF) numa imagem plana;
   - `link_modules.py` / `link_libc.py` ligam libc, Fios e os módulos de som do usuário;
   - `content_profile.py`, `sotc_cpu.py` (correções de CPU), `sotc_modes.py` (60 FPS, AF 16x,
     cvars do motor);
   - se existe atualização (`CUSA08809-UPDATE`/`-patch`) com `eboot.bin`, usa a imagem dela.
3. **`bb-probe.exe`** (o "jogo"): carregador em C (`src/probe.c`) + runtime + núcleo de vídeo
   (`gpu/`). Carrega a imagem **abaixo de 2 GiB** (o jogo guarda ponteiros em 31 bits),
   cria as threads/fibras do jogo e começa.

### Diretórios

| Pasta | Conteúdo |
|---|---|
| `src/` | carregador e runtime (memória, arquivos, saves, áudio, pad, serviços, fibras, SotC) |
| `gpu/shadps4/` | núcleo de vídeo (video_core, shader_recompiler, gnmdriver, videoout) |
| `gpu/shim/` | ponte entre o runtime e o núcleo de vídeo, janela SDL, overlay ImGui |
| `gpu/sotc/` | correções de CPU (SSE4a, red zone) portadas do fork |
| `scripts/` | preparação do jogo |
| `launcher/` | `SotC.exe` (sotc_launcher_win.py, sotc_discovery.py, ícones) |
| `tools/` | testes automatizados, benchmark, A/B, perfilador |
| `packaging/windows/` | `package_sotc.sh` → `dist/SotC-PC.zip` (recusa `.sprx/.prx`) |
| `docs/sotc/` | este documento, README do pacote, plano do "caminho B" |

## 3. Linha do tempo

### 07/10 — o jogo inicia
- Imports casados por NID; funções do SotC num arquivo próprio (`runtime_sotc.c`).
- Janela extra de memória `0x700000000–0x800000000` (o jogo mapeia em endereço fixo).
- O jogo chega à própria inicialização.

### 08/10 — jogável
- **Fibras** (`runtime_fiber.c`), **correções de CPU** (SSE4a, red zone) e **imagem abaixo de
  2 GiB** → primeiros quadros (falcão no cânion).
- Correções de GPU do fork aplicadas ao núcleo do bbport → abertura sem polígonos pretos.
- **Virada:** núcleo de vídeo do **nosso fork do shadPS4** no lugar do do bbport → logos,
  menus com texto, save carrega, campo aberto a 30 FPS, 10 min sem queda.
- Crash silencioso resolvido: o rastreador de páginas protegia a pilha das fibras.
- **Áudio real** com os módulos do usuário; lançador `sotc.py`/`SotC.bat`; pacote Windows.
- **Modos**: AF 16x e 60 FPS (patch no carregamento, `BB_VBLANK_HZ=120`).
- `SotC.exe` (lançador gráfico), controles do bbport 0.4 (teclado + controle juntos,
  remapeamento), câmera no mouse, resolução de saída 720p–4K, modo PS4 Pro, efeitos do motor.

### 08–09/10 — desempenho
- Benchmark fixo: o **demo da tela de título** (mesmo percurso sempre).
- Ganhos: cache de informação de shaders, HLE do compute que preenche tabelas, cache de
  ponteiros de memória por thread, cvars de culling do Pink, guard do heap BPE, sync de buffers
  sem trava, draws indiretos com argumentos na CPU viram diretos, gravação Vulkan em thread
  própria, caches de descrição/busca de imagens, menos falhas de escrita, envio periódico por
  tempo (`SOTC_FLUSH_US=500`).
- Resultado no demo (60 FPS, i9-13900K + RTX 2060 SUPER): **média 37–45 → ~67 FPS**, trecho
  mais pesado (ponte do cânion) **~17 → 29–34 FPS**.

### 12/10 — lançador, publicação, saves, texturas
- **0.0.8 pública**: biblioteca de jogos, busca automática, troca de teclas, ícone novo, opção
  de envio de trabalho à GPU (AMD/Intel).
- **0.0.9 pública**: tela de configuração inicial (só pede a pasta principal, como o shadPS4),
  atualização como no shadPS4 (`-UPDATE`/`-patch` por cima do jogo base), **DLC** em pasta ou
  **`.pkg` sem instalar** (as 6 DLCs listadas ao jogo).
- Projeto reunido numa **pasta única** (`SotC-PC`).
- **Gravação corrigida**: o jogo nunca gravava ("sem espaço").
- **Streaming de texturas** (`GET_LOD_STATS`): texturas nítidas de perto, cascatas com as
  cortinas de água, superfície da água com ondulação.
- **Lista de saves na tela** para carregar e gravar, com **exclusão de save**.

## 4. Funcionalidades atuais

- **Lançador** (`SotC.exe`): configuração na primeira abertura; acha jogo, atualização, DLCs,
  saves do shadPS4 e módulos de som; biblioteca; opções de imagem (resolução de saída, FSR 1,
  nitidez, AF 16x, 60 FPS, PS4 Pro, efeitos), controles (teclado/controle/mouse, remapeamento),
  envio de trabalho à GPU; atalho na área de trabalho com o ícone do jogo.
- **Jogo**: roda do começo ao fim no modo normal; áudio real; saves (gravar, carregar, apagar);
  DLCs; atualização 1.01; modo PS4 Pro (Cinematográfico/Desempenho no menu do jogo).

## 5. Correções técnicas principais

| Problema | Causa | Correção |
|---|---|---|
| Crash silencioso sem mensagem | página da pilha de fibra protegida pelo rastreador da GPU | pilhas de fibra registradas e excluídas do rastreio |
| Ponteiros do jogo quebrados | o jogo guarda ponteiros em 31 bits | imagem carregada abaixo de 2 GiB |
| Polígonos pretos na abertura | correções de GPU do fork ausentes | núcleo de vídeo do fork |
| Tela preta intermitente | otimizações do bbport incompatíveis com o SotC | núcleo do fork; leituras precisas da GPU |
| Jogo nunca gravava | o port dizia que cada save ocupava 1 GiB | tamanho real dos saves |
| Carregar entrava em laço / cada gravação criava slot novo | diálogo de lista "terminava" sem escolha | lista desenhada na tela (overlay ImGui) |
| Texturas borradas, água preta, cascatas sem cortina | comando `GET_LOD_STATS` ignorado → o jogo nunca carregava os mips finos | estatísticas emuladas a partir das texturas usadas; texturas reenviadas quando o jogo mapeia memória nova |
| Fila da GPU travava com a gravação em thread | o apresentador esperava um tick antes de ele ser enviado | espera do envio antes de apresentar |

## 6. Problemas conhecidos (prioridade)

1. **Corrupção de memória com o streaming de texturas.** Pedir resolução máxima (mip 0/1) para
   tudo faz o jogo corromper a própria memória em 1–4 minutos; com o limite atual (mip 2,
   512×512) o demo roda inteiro, mas **carregar outro save sem reiniciar o jogo pode fechá-lo**.
   Recomendação: reiniciar o jogo antes de trocar de save. Testado e **descartado** como causa
   (12/10): rótulos EOP escritos cedo (`SOTC_EOP_DEFER=1` escreve quando a GPU termina: o FPS cai
   pela metade e a falha continua), a cópia HLE marcando a faixa inteira como escrita pela GPU
   (corrigida para marcar só os pedaços; a falha continua) e recusas de memória do runtime (não
   há). O sintoma é sempre memória reaproveitada pelo jogo ainda lida/escrita com dados velhos
   (nós do heap, descritores e shaders com lixo) por volta de 250–270 s do demo com mip 0/1.
2. **Sombras pretas**: áreas na sombra sem luz ambiente (não piorou com as mudanças recentes).
   Pista (captura RenderDoc do templo da abertura, ~178 s): uma entrada de meia resolução dos
   passes de iluminação (960×540, A2B10G10R10, lida por ~16 desenhos de luz) **nunca é escrita
   no quadro e fica em zero** — provável oclusão de ambiente/luz indireta faltando. Ainda não se
   sabe qual passe deveria escrevê-la (nenhuma escrita como imagem nem como buffer encontrada).
3. **Água**: lago opaco/liso em alguns lugares; balanço das ondas não confirmado.
4. **Fechamento no demo da tela de título** após vários minutos (mesma família do item 1).
5. Os saves antigos copiados do shadPS4 aparecem com a etiqueta "Profile" (a etiqueta se
   corrige ao gravar por cima).
6. AMD/Intel: as otimizações de envio estão desligadas por padrão e pouco testadas.

## 7. Diagnóstico (variáveis de ambiente)

| Variável | Função |
|---|---|
| `SOTC_FPS=1` | FPS e leituras da GPU no log a cada 5 s |
| `SOTC_SAVE_TRACE=1` | registra as chamadas de save |
| `SOTC_LOD_STATS=0` / `SOTC_LOD_LEVEL=n` / `SOTC_LOD_TRACE=1` | streaming de texturas: desligar, nível pedido, registro |
| `SOTC_MAP_INVALIDATE=0` | não reenvia texturas quando o jogo mapeia memória |
| `BB_WRITE_LOG=1` | registro das escritas do port na memória do jogo (despejado numa falha, com totais por origem) |
| `SOTC_RDOC_TRIGGER` + `SOTC_PLAY_WRAP` | captura de RenderDoc de um envio da GPU (`renderdoccmd capture`) |
| `SOTC_SHOT_OVERLAY=1` | prints com o overlay (lista de saves) |
| `BB_FRAME_DUMP_TRIGGER` | print do quadro quando o arquivo aparece |
| `BB_PAD_FILE` / `BB_PAD_RECORD` / `BB_PAD_REPLAY` | controle por arquivo, gravar/repetir percurso |
| `SOTC_PROFILE=<thread>` | perfilador por amostragem |
| `SOTC_FLUSH_US`, `SOTC_RB_AHEAD`, `SOTC_RECORD_THREAD`, `SOTC_INDIRECT_DIRECT`, `SOTC_FILL_HLE` | otimizações (ligar/desligar para testes) |

Ferramentas: `tools/sotc_play.py` (roteiro: `t:cross`, `t:shot`, `t:rdoc`…),
`tools/sotc_bench_attract.sh` (benchmark), `tools/sotc_intro_ab.sh` (A/B no rio da abertura),
`tools/profile_sym.py`.

## 8. Compilar, empacotar, testar

```bash
# compilar (MSYS2 CLANG64 em I:\msys64)
TMP=$(cygpath -w /tmp) PATH=/i/msys64/clang64/bin:/i/msys64/usr/bin:$PATH ninja -C out/gpu bb-probe bb-gpu-capabilities
cp out/gpu/bb-probe.exe out/gpu/bb-gpu-capabilities.exe out/
# pacote (dist/SotC-PC.zip e dist/SotC-PC/ com os saves preservados)
bash packaging/windows/package_sotc.sh
# benchmark (60 FPS, com as cvars de culling do jogo real)
BENCH_CVARS="doIndexBufferCulling=0 doSunShadowIndexBufferCulling=0" bash tools/sotc_bench_attract.sh
```

Regras do projeto: commits como `AjncSystem <AjncSystem@users.noreply.github.com>`; nunca
distribuir firmware da Sony (`.sprx`); despejos grandes no disco I:.

## 9. Próximos passos

1. **Estabilidade do streaming** (item 1 dos problemas): rótulos EOP escritos quando a GPU
   termina ("caminho B", etapa já prototipada com `VK_EXT_external_memory_host`), depois
   liberar a resolução máxima das texturas.
2. **Sombras e luz ambiente**: capturar uma cena com RenderDoc e seguir o passe de iluminação.
3. **Água**: shader da superfície (desenho achado na captura) e animação das ondas.
4. Indicador de progresso com % na tela preta inicial.
5. Testes em AMD e Intel.

### Sobre DirectX 12

O port **já é nativo x86-64 do Windows**: o código do jogo roda direto no processador. A única
parte "emulada" é a GPU, que hoje é traduzida para **Vulkan**. Trocar para DirectX 12 significaria
reescrever o núcleo de vídeo inteiro (milhares de arquivos de tradução de comandos e shaders
GCN → SPIR-V) para D3D12/DXIL, sem ganho real: o Vulkan funciona em todas as placas do Windows
(NVIDIA, AMD, Intel) e o desempenho depende da tradução, não da API. Uma engenharia reversa
"completa" (recriar o renderizador do jogo em DirectX, sem tradução de GPU) seria outro projeto,
de muitos meses. O caminho que traz resultado é continuar corrigindo a tradução atual.
