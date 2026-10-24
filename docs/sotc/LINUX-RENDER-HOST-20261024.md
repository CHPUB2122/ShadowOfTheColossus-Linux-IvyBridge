# Diagnóstico do teste gráfico do host — 24/10/2026

Execução analisada: `out/logs/render-20261024T131245Z-6768`, processo 6783,
limite de 30 s, saída 142. Branch `linux-ivybridge`, HEAD `38f2763`.
Antes de recompilar, os hashes de `bb-probe`, `libbbgpu.so` e dos artefatos de
configuração foram conferidos contra `run.json`: todos correspondiam.

Backup anterior às edições desta etapa:
`/home/chpub/Backups/sotc-host-followup-20261024T131840Z/`.
O tar e o manifesto SHA-256 foram verificados por releitura dos 1.635 arquivos.
Incluem os binários usados no host, fontes, diff, logs recebidos e capturas.
Os logs originais e os patches de CPU/RDTSC/UD2/FSR permanecem intactos.

## O que mudou em relação ao travamento anterior

O antigo laço `+0x25cdb0..+0x25cdbc` não aparece na pilha atual. O log confirma
26 RDTSC substituídos, zero sites identificados deixados no TSC nativo. Houve
execução do command processor, compilação de shaders e preparação de buffers
VideoOut; portanto a execução avançou além do ponto anterior.

O watchdog do Linux é um `alarm(timeout_seconds)` contado desde o início do
loader. **142 significa que terminou o prazo do teste.** Esse watchdog não
mede ausência de flips. Não foi removido nem transformado em sinalização de
eventos para contornar uma espera.

Pilhas simbolizadas com os binários correspondentes ao teste:

| Thread | Estado no dump final |
|---|---|
| Principal, 6783 | Handler de fault GPU → `InvalidateMemoryOnGuestFault` → `BufferCache::ReadMemory` → `SendCommand<true>` → semáforo do callback de início de readback |
| GpuDraw, 6790 | `Liverpool::BackLoop`, espera temporizada por trabalho |
| GpuCommandProcessor, 6792 | `Liverpool::Process`, espera na condição de submissão |
| RenderFlip, 6832 | `EqueueInternal::WaitForEvents`, chamado pelo guest em `+0x960f7` |
| Game Render, 6833 | Event flag, chamado pelo guest em `+0xbd942` |
| Shadow Game Update, 6842 | Event flag, chamado pelo guest em `+0x5b996f` |
| SceFiosIO, 6825 | Caminho de `do_pread`; várias amostras em estado D/espera de páginas de arquivo |

O dump de threads é sequencial. Uma espera do principal e uma GPU ociosa em
instantes próximos não comprovam, sozinhas, perda de um callback ou deadlock.
Os contadores de CPU continuaram aumentando entre 10 e 25 s:

| Thread | Ticks em 10 s | Ticks em 25 s |
|---|---:|---:|
| Principal | 361 | 586 |
| GpuDraw | 263 | 996 |
| GpuCommandProcessor | 317 | 1193 |
| BPE JobWorker 6828 | 485 | 1483 |

Isso deixa em aberto trabalho lento, repetição de faults/readbacks e bloqueio
de uma fase específica. Não houve SIGSEGV/SIGILL **fatal** registrado. Faults
tratados pelo rastreamento de páginas continuam fazendo parte da execução.

## Buffers e imagem observada

As três capturas de `user/screenshots/*20261024_101251*game*.png` são 1920×1080,
inteiramente pretas e idênticas (SHA-256
`e320cebac9889dbcf22003cd5435c75b522b3a3f6a16b0db8a052fe3d6e471c6`).
Vieram de `Presenter::PrepareFrame`, chamado por `SubmitFlipInternal`, e são
capturadas antes da composição do overlay. Isso comprova acesso a buffers
registrados do jogo e a conclusão das cópias necessárias às capturas. Não
comprova um quadro com conteúdo nem apresentação contínua.

Elas cobrem apenas a primeira sequência de três buffers, por volta de 6 s.
Não registram a logo/opções relatadas depois. A tela de carregamento do port
desenha o título SHADOW OF THE COLOSSUS, arco e texto de carregamento; não há
logo Sony nessa implementação. A logo relatada é compatível com conteúdo do
jogo/vídeo, mas sua origem exata e as opções precisam de captura posterior.

O log de fim do carregamento também tem uma limitação: `Render` pode retornar
em `!Visible()` antes de registrar a transição para overlay oculto. Assim,
ausência de `loading screen: hidden` não comprova ausência de flips.

## Sincronização e instrumentação preparada

Na fila RenderFlip, `ident 1 / filter -11` é **User**; `ident 6 / filter -13`
é o evento de flip. Eventos GNM usam **GraphicsCore (-14)**. Não se deve
interpretar aquele evento de usuário como uma conclusão GNM.

O log recebido não identifica os handles de `PS4SyncEvent` nem seu último
setter. Portanto não permite atribuir com segurança a thread responsável por
cada sinal. Foram acrescentados diagnósticos específicos, sem alterar a
ordem dos callbacks, os critérios de espera ou os bits dos eventos:

- `SOTC_RENDER_DIAG=1`: contadores cumulativos a cada 5 s e no watchdog para
  entrada GNM, buffers enfileirados/iniciados/finalizados, chamadas de draw e
  dispatch, submissões Vulkan aceitas, flips solicitados/enfileirados/retirados,
  eventos encontrados/ausentes/consumidos e readbacks iniciados/concluídos.
- Os contadores distinguem apresentação de buffers do jogo de apresentação
  auxiliar/repetida. Uma chamada concluída não prova pixels válidos. Submissão
  Vulkan aceita também não equivale a conclusão de execução na GPU.
- `SOTC_SYNC_DIAG=1`: handle da flag, TID que espera, número de sets/grants e
  TID/endereço do último setter. O nome compartilhado deixa de ocultar qual
  instância está em espera.
- Se um dump interromper o handler de memória GPU, registra também o PC e
  endereço originais do fault. Antes, a caminhada de frames parava na pilha
  alternativa e perdia justamente essa instrução guest.

Os contadores são amostrados individualmente, sem congelar as threads. Buffers
indiretos também contam como buffers iniciados; contagens de chamadas não são
uma medição de FPS. A instrumentação fica desligada nas execuções normais.

## Verificações locais

- Compilação existente com `-march=ivybridge`, sem BMI/AVX2, e CTest **11/11**.
- Fixture da implementação real de Equeue: 1.000 entregas concorrentes de
  flip, consumo, identidade do evento GNM e registro ausente: **PASS**.
- Fixture dos imports reais de event flag: 1.000 handshakes, clear automático,
  isolamento de flags com o mesmo nome e espera longa seguida de set real:
  **PASS**. O diagnóstico mostrou corretamente TID e último setter.
- Sampler SIGUSR2 e snapshot de contadores no SIGALRM: **PASS**.
- Parser dos contadores e classificação das três imagens existentes: **PASS**.
- `py_compile` e `git diff --check`: **PASS**.

Fontes e logs dos fixtures, símbolos das pilhas e resultados estão em
`out/logs/host-analysis-20261024T131840Z/`. Uma primeira tentativa de compilação
referenciou um nome de rasterizer fora do escopo; foi corrigida para obter a
instância pela interface existente. O log da falha foi preservado.

Esta sessão continua sem `/dev/dri` e sem ptrace. A execução local completa
para no SDL, antes do motor, com `No available video device`; isso não valida
nem invalida o comportamento gráfico no host. Não foi aplicada uma correção
especulativa de renderização nem declarada renderização contínua.

## Próximo teste real

```sh
cd /home/chpub/Projetos/sotc-linux-ivybridge
python3 tools/sotc_render_debug.py \
  --game '/mnt/HD RAID/Jogos/Ports I.A/CUSA08809' \
  --timeout 120 --no-gdb
```

O script preserva os argumentos e dados preparados. Solicita novas capturas a
cada 10 s e pilhas de threads selecionadas a cada 20 s, sem acordar seus waits.
Coleta mapas, status, I/O, memória e pressão de memória/I/O. `result.json`
distingue prazo absoluto de erro e inclui contadores e análise das novas
capturas. O código 142 continua esperado quando os 120 s terminam.

Se o progresso parar, os últimos contadores e as flags indicarão qual fronteira
investigar. Para obter também os objetos/locals do debugger, omitir `--no-gdb`;
breakpoints por draw estão desligados por padrão. GDB ainda pode alterar bastante
o tempo devido aos SIGSEGV tratados pelo page tracker, portanto não comparar FPS
desse modo com a execução normal.
