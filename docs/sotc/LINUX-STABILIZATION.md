# Estabilização Linux — 24/10/2026

Plano e registro desta etapa. Aceitação de gameplay continua dependente do host
com RADV; este ambiente não tem `/dev/dri`, dispositivos de controle ou acesso
à sessão gráfica. Não há validação local de imagem ou FPS.

## A — Preservação e reprodução

- Branch `linux-ivybridge`, HEAD `38f2763d6d4d3f4b616512e43ff635609d362664`.
- Referência recuperável anterior às edições:
  `/home/chpub/Projetos/.sotc-backups/20261024T172655Z/BASELINE.json`.
  `project/` contém a cópia integral, inclusive `.git`, arquivos não rastreados,
  submódulos, binários, caches, saves e evidências. `manifest.json` foi verificado
  por releitura: **39.147 arquivos, nenhuma divergência**. O commit sozinho não
  representa o estado funcional, que inclui as modificações não commitadas.
- Nenhum reset, clean, remoção de cache/save ou atualização de submódulo.
- Evidências novas: `out/logs/stabilization-20261024T173019Z/`.
- Reprodução com guest sintético válido, sem GPU, executando um laço contínuo:
  binário anterior encerra em **10,16 s, código 142**, pelo `alarm(10)` padrão.
  O alarme é prazo absoluto de sessão, não detecção de ausência de progresso.

## B — Inicialização e armazenamento

Comparação de caminhos antes da alteração:

| Entrada | Preparação | Perfil | Prazo Linux |
| --- | --- | --- | --- |
| `tools/sotc_render_debug.py` | reutiliza artefatos | `--user`, padrão `ROOT/user`; ignora `SOTC_USER_DIR` | explícito, 30–600 s |
| `run.sh` | compila e chama `sotc.py` | herdado de `sotc.py` | 10 s implícitos |
| `sotc.py` | pode regenerar imagem/módulos e sempre cmdline/patches | `SOTC_USER_DIR` ou `ROOT/user`; `BB_GPU_USER_DIR` pode discordar | 10 s implícitos |
| `out/bb-probe` | somente argumentos | `--user` ou `user` relativo ao cwd; GPU inicializa paths antes do main | 10 s implícitos |

O diagnóstico bem-sucedido `render-20261024T155813Z-22316` usou os mesmos
artefatos disponíveis, diagnósticos principais zerados, prazo de 300 s e terminou
com 0 após 103 s. Isso e a reprodução do laço comprovam o defeito do prazo padrão;
não comprovam que toda espera longa de `PS4SyncEvent` seja causada por ele.
O aviso de troca de produtor aparece também em execuções que terminam com 0;
isoladamente não comprova corrupção ou deadlock.

Implementação: launcher normal usa artefatos existentes, cwd fixo e nenhum
prazo de sessão. A preparação continua explícita. Produção desliga os diagnósticos
e preserva os defaults de threading. Produção/diagnóstico resolvem o mesmo perfil,
rejeitam configuração conflitante, verificam backup dos saves e usam trava por
diretório de usuário. Não há migração nem restauração automática de progresso.

## C — Gráficos

Ler traces e SPIR-V existentes; associar shaders aos passes antes de propor
alterações. As capturas listadas nos relatórios anteriores não estão mais em
`user/screenshots` neste checkout (diretório vazio); hashes e estatísticas em
`result.json` não substituem os pixels nem captura de um draw. Não declarar
correção de materiais sem comparação no hardware real.

## D — Desempenho

Instrumentação desligada em produção. Não reduzir resolução/qualidade nem
desativar CP/recorder. Medir na mesma cena com cache aquecido, comparando tempo
de quadro e FPS; separar compilação, carregamento, apresentação e gameplay.
Validar qualquer otimização gráfica na RX 580 antes de adotá-la como default.

## E — Validação

Compilar e executar CTest, testar launcher com processo real descartável,
testar persistência nas implementações reais de SaveData/File em perfil temporário,
conferir hashes CPU/FSR/cache/save contra a referência. Registrar separadamente
o resultado do teste sintético de deadline e as limitações de GPU/áudio/controle.
Gameplay no host deve incluir três aberturas, save/reabertura entre métodos,
Wander, Agro, primeiro colosso e saída normal antes de declarar estabilização.

## Resultados locais

Compilação com flags Ivy Bridge, PGO/LTO off e CTest **14/14** aprovados.
Logs: `out/logs/linux-20261024T174323Z-2/`.

| Verificação | Resultado e limite |
| --- | --- |
| Deadline do binário anterior | 142 após 10,16 s, mesmo com guest executando continuamente |
| Novo default, mesmo guest | continua vivo além de 11 s; encerrado somente pelo harness |
| `--timeout 1` | 142 após 1,16 s, dump preservado |
| CPU da imagem real | 58.984 funções, 5.169 sites curtos relocados, SSE4a/BMI1/LZCNT/MOVBE emulados |
| RDTSC da imagem real | 26 substituídos, 0 sites identificados restantes no TSC nativo |
| Persistência sintética | perfil/progresso escritos e reabertos em outro processo/cwd; backup antigo não substitui principal recente |
| Launcher normal | comando/ambiente conferidos; execução local para no SDL com 23 por ausência de vídeo |
| Preservação por SHA-256 | 10.303 arquivos protegidos sem alteração, incluindo CPU/FSR/saves/cache e imagens preparadas |
| Biblioteca gráfica | `out/gpu/libbbgpu.so` idêntica à referência anterior às edições |

`preservation.json`, `deadline-after.json`, `game-cpu-patches.log` e
`launcher-no-gpu.log` registram esses resultados no diretório de evidências da
etapa. Não houve alteração de algoritmo de CPU, relógio, tratamento UD2 ou FSR.
O loader muda o default do prazo absoluto e imprime sua natureza quando solicitado.
Os waits/eventos do jogo mantêm sua semântica anterior.

## Saves e armazenamento

Os cinco logs solicitados mostram leitura de Profile/Progress em modo somente
leitura, seguida de montagens de Profile para escrita. O modo é solicitado pelo
próprio jogo naquele mount; não demonstra proteção do diretório do host contra
gravação. O runtime só faz `.sce_backup` no unmount de um mount gravável. Não se
alterou o contrato de mounts para forçar escrita durante a leitura.

Só foi encontrado um conjunto ativo neste checkout, em
`user/savedata/1/CUSA08809`. `.sce_sys` são metadados e `.sce_backup` são cópias
dos mesmos slots. Não se demonstrou troca de progresso nos dados recebidos.
Os scripts Windows antigos `sotc_play.py`, `sotc_run.sh` e `gameplay_bench.py`
usam `out/user`; o último também apaga seu alvo para restaurar templates.
Eles não foram usados nesta etapa.

Agora `--user` escolhe explicitamente o perfil; sem ele, `SOTC_USER_DIR` e
`BB_GPU_USER_DIR` devem concordar. Um único deles também é aceito. Paths relativos
de configuração são resolvidos contra a raiz do projeto. O diretório existe
antes de carregar a biblioteca GPU, que calcula paths em inicializadores estáticos.
O diagnóstico usa o mesmo construtor de argumentos e a mesma resolução de perfil.
Cada sessão guarda uma cópia verificada `savedata-before`, hashes antes/depois
e a lista de arquivos alterados. Não há migração/restauração automática.

A trava protege produção e diagnóstico novos. Invocar `bb-probe` manualmente ou
scripts antigos pode contorná-la. Um checkpoint real do jogo e sua reabertura
continuam pendentes de validação no host.

## Evidência gráfica nova

Validação somente leitura dos **3.516 SPIR-V** do cache, usando
`spirv-val --target-env vulkan1.3 --scalar-block-layout`:
**3.515 válidos e um inválido**.

Arquivo: `user/cache/CUSA08809_nodma/0x00000000df2d1d0b_0.spv`.
Três instruções extraem o índice 2 de `%1581`, declarado como vetor de duas floats:

```text
%1581 = OpConstantComposite %f32vec2_id ... ...
%1584 = OpCompositeExtract %f32_id %1581 2
```

A permutação `_1.spv` passa. `spirv-validation.json` e os dois dumps `.spvasm`
preservam a evidência. Esse shader aparece no cache e em mensagens de compilação
anteriores, mas não identificado como draw de personagem nos cinco traces.
Não há GCN original dumpado em `user/shader` para reproduzir sua tradução completa.
Inspeção dos emissores de vetores/buffers e passes de simplificação ainda não
estabeleceu qual deles produziu o tipo incorreto. **Nenhum shader/cache foi
editado, removido ou substituído. A causa das cores fluorescentes continua aberta.**

Foram encontrados candidatos do caminho dinâmico. Exemplo:
`render-20261024T145802Z-17201/game.log:1344`, VS `0xeea31ea6`, FS `0xe86411f9`,
mask `0x7f`, perto de `RenderGBufferBakedPerProbe` e
`kRS_GBuffer_Ambient_Dynamic_Motion`. `dynamic-draw-candidates.json` guarda
endereços/formatos/MRTs. Marcadores assíncronos próximos não identificam Wander
ou Agro conclusivamente. É necessária captura de pixel history/draw para ligar
o primeiro material incorreto aos inputs/outputs. Os scripts `tools/rdoc/` podem
examinar uma captura; não há `.rdc` disponível nesta sessão.

O SIGSEGV histórico de `render-20261024T144103Z-15703` ocorreu em
`Rasterizer::TraceGraphicsTargets`; não foi timeout. O fonte já recebido contém
guardas para slots MRT inativos/ColorBuffer inválido. Esse código foi preservado,
sem atribuir uma correção nova ou validação em GPU a esta etapa.

## Desempenho, áudio e controle

Produção remove `SOTC_PASS_TRACE`, `SOTC_FPS` e `SOTC_CMD_STATS` do ambiente:
eles testam presença, portanto `=0` não basta. CP e recorder ficam explicitamente
ativos. Experimentos com threads desligadas continuam disponíveis no diagnóstico.
`--benchmark` habilita apenas o timing por apresentação existente (`SOTC_FRAME_LOG=1`),
sem prazo/capturas periódicas. `tools/sotc_frame_report.py` calcula FPS/percentis
de intervalos consecutivos e recusa percentis individuais de logs agrupados.

Os logs históricos amostram a cada 30 frames e não comprovam cenas equivalentes.
`historical-frame-timing.json` registra suas janelas/ambientes, mas **não demonstra
ganho de FPS desta etapa**. `/proc` mostra GpuComm/GpuDraw com aproximadamente
88–95 ticks/s nos últimos 30 s de vários testes instrumentados e carga elevada
nos BPE workers. Isso evidencia pressão de CPU naquele regime. Sem GPU time e
cena equivalente de produção, não quantifica o gargalo final. Não se alteraram
qualidade, resolução, barreiras, LDS ou configurações de driver para inferir ganho.

O último teste funcional recebido registra Xbox 360 Controller e backend PipeWire.
Também registra **Ngs2 silent audio**. `out/link.json` contém apenas libc/Fios2;
`libSceNgs2.sprx` e `libSceUlt.sprx` não estão nos diretórios consultados. Abrir
portas PipeWire não prova áudio do jogo. Essa pendência exige os módulos do dump
próprio e preparação separada, preservando o baseline. O teste SDL de pad passa;
controle físico e som audível não puderam ser revalidados neste ambiente.

## Comandos Fish e aceitação no host

O `sotc.ini` local (ignorado pelo Git) aponta para o dump/perfil desta missão.
Uso normal, sem GDB, preparação ou limite de sessão:

```fish
cd /home/chpub/Projetos/sotc-linux-ivybridge
./run.sh
```

Cada sessão imprime `out/logs/play-.../game.log`. `run.json` registra os binários,
argumentos/ambiente e saves iniciais; `result.json`, saída/saves finais. `0` é
saída normal; `139`/SIGSEGV exige investigação; `142`/SIGALRM em teste com prazo
explícito é timeout. Recompilação é explícita: `bash build.sh --test` ou
`./run.sh --build`. Para conferir a configuração sem iniciar: `./run.sh --dry-run`.

Alternar com diagnóstico reduzido, usando o mesmo perfil:

```fish
env SOTC_RENDER_DIAG=0 SOTC_SYNC_DIAG=0 SOTC_FRAME_LOG=0 \
  python3 tools/sotc_render_debug.py --no-gdb \
  --game '/mnt/HD RAID/Jogos/Ports I.A/CUSA08809' \
  --timeout 300 --shot-interval 0 --stack-interval 0
```

Validar três aberturas normais: carregar o mesmo progresso, andar com Wander,
montar Agro e alcançar o colosso. Salvar pelo mecanismo normal do jogo e fechar
normalmente. Reabrir por cada método; comparar progresso e manifests de saves.
Mudar um hash comprova escrita, mas o avanço correto precisa ser visto no jogo.

Benchmark sem restaurar templates: mesma câmera/local, 1080p/opções constantes,
cache aquecido. Manter os últimos 60 s na cena escolhida e sair normalmente:

```fish
./run.sh --benchmark
set sessao (ls -dt out/logs/play-* | head -n 1)
python3 tools/sotc_frame_report.py "$sessao/game.log" --last-seconds 60
```

Repetir três vezes, identificando a cena e conservando os logs. Os tempos medem
apresentações do jogo, não execução GPU; existe overhead de medição. A meta de
30 FPS estáveis permanece aberta, sem estimativa nova nesta sessão.

Captura explícita de Wander/Agro/colosso, conservando threads e qualidade:

```fish
env SOTC_RENDER_DIAG=0 SOTC_SYNC_DIAG=0 SOTC_FRAME_LOG=0 \
  SOTC_CP_THREADS=1 SOTC_RECORD_THREAD=1 \
  python3 tools/sotc_render_debug.py --no-gdb \
  --game '/mnt/HD RAID/Jogos/Ports I.A/CUSA08809' \
  --graphics-profile baseline --graphics-diag \
  --timeout 300 --shot-interval 15 --stack-interval 0
```

Esse comando diagnóstico custa FPS. Fechar normalmente após capturar. Baseline
gera cmdline isolada, preserva `out/cmdline.bin` e coloca PNGs em `user/screenshots`.

## Recuperação e situação da missão

Executar a referência anterior em sua própria árvore, com o progresso atual:

```fish
set referencia /home/chpub/Projetos/.sotc-backups/20261024T172655Z/project
cd "$referencia"
env SOTC_RENDER_DIAG=0 SOTC_SYNC_DIAG=0 SOTC_FRAME_LOG=0 \
  python3 tools/sotc_render_debug.py --no-gdb \
  --game '/mnt/HD RAID/Jogos/Ports I.A/CUSA08809' \
  --user /home/chpub/Projetos/sotc-linux-ivybridge/user \
  --timeout 300 --shot-interval 300 --stack-interval 0
```

Fechar a outra sessão antes: a ferramenta antiga não participa da trava nova.
Não copiar `project/user` sobre o perfil ativo. O RUNPATH usa `$ORIGIN/gpu`,
portanto a cópia encontra a biblioteca correspondente preservada.

**Missão incompleta:** o defeito do prazo absoluto e os caminhos dos launchers
foram corrigidos/testados localmente. Gameplay repetido, checkpoint real,
materiais corretos, som audível e desempenho da RX 580 ainda dependem do host.
Não há correção gráfica comprovada antes/depois nem resultado novo de FPS.
Nenhuma alteração experimental foi promovida ao renderer.
