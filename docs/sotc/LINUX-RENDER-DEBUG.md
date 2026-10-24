# Continuação Linux Ivy Bridge — 24/10/2026

Continuação com o teste gráfico real do host e novos diagnósticos:
[LINUX-RENDER-HOST-20261024.md](LINUX-RENDER-HOST-20261024.md).

Estado recuperado: branch `linux-ivybridge`, HEAD `38f2763`. Foram preservadas
as alterações locais de `src/probe.c`, `gpu/sotc/cpu_patches.cpp`,
`gpu/sotc/sotc_patches.cpp` e do submódulo FSR-Vulkan. A correção de repetição
dos UD2 registrados continua presente. Nenhum arquivo original do jogo foi editado.

Backup anterior à primeira edição:
`/home/chpub/Backups/sotc-20261024T122539Z/`. Contém `snapshot.tar`,
`manifest.json`, diffs binários, status, commits e submódulos. Os 1.897 arquivos
do tar foram relidos e conferidos com os SHA-256 do manifesto.

## Causa reproduzida

As seis execuções com pilhas preservadas param a thread principal entre
`+0x25cdb0` e `+0x25cdbc`, dentro do cálculo de tempo, antes do próximo quadro.
Esse laço subtrai um passo de tempo de um acumulador `float`. Não é uma espera
por mutex. As pilhas do command processor e da draw thread mostram espera por
trabalho naquele instante; isso não prova ausência de submissões anteriores.

O kernel oferece somente `hpet acpi_pm` como clocksources e usa HPET. Um teste
de ping-pong com afinidade por thread e RDTSC serializado encontrou cerca de
**54.122.982.700 ticks de diferença entre CPU 0 e CPUs 1–7**, aproximadamente
15,95 segundos a 3,39 GHz. A presença de `constant_tsc` no CPUID não garante
que os contadores de núcleos diferentes estejam sincronizados.

Foi executada a função original de relógio do jogo (`+0x324e0`) em uma cópia
temporária em memória, com origem lida no CPU 1 e leitura posterior no CPU 0:

```text
Original: delta_seconds=5425512946.937334061
float_delta=5.42551296e+09
step=0.0333333351
float_delta - step = float_delta
```

A subtração unsigned dos timestamps volta para perto de UINT64_MAX. Depois
da conversão para `float`, o passo não altera o acumulador: o laço não termina.
As esperas de `PS4SyncEvent` e da fila de flip são consequências compatíveis
com a thread principal impedida de produzir o próximo trabalho. Não foi
necessário sinalizar eventos artificialmente.

Com a substituição real de RDTSC pelo trampoline corrigido, a mesma função,
na mesma migração entre CPUs, retornou aproximadamente 80 microssegundos.
A reprodução preservada em `out/logs/clock-fix-20261024T124038Z/clock-repro.log`
mostra o antes/depois. Os fontes dos dois diagnósticos também estão nesse
diretório (`tsc-audit.c`, `clock-repro.cpp`); não contêm arquivos do jogo.

## Correção

- No Linux, quando o kernel exclui `tsc` de `available_clocksource`, o loader
  seleciona `CLOCK_MONOTONIC`. `SOTC_TSC=monotonic` força essa seleção;
  `SOTC_TSC=native` mantém o comportamento anterior para comparação.
- O relógio inline do eboot, `sceKernelReadTsc` e `sceKernelGetTscFrequency`
  compartilham a escala de 1 GHz. Não basta alterar somente os imports:
  o motor lê RDTSC diretamente.
- O trampoline existente ganhou preservação System V de RDI, RSI e todos
  os 16 registradores YMM completos, além dos demais GPRs e flags que já
  preservava. A red zone continua protegida. Usa AVX disponível no Ivy Bridge.
  O caminho Win64 continua separado.
- O loader rejeita a execução se a seleção monotônica deixar um RDTSC
  identificado sem patch, evitando misturar unidades/origens de relógio.
- `--check-cpu-patches` valida o eboot preparado sem inicializar a GPU nem
  executar o jogo. Nesta imagem: **26 RDTSC substituídos, zero restantes**;
  os 5.169 sites curtos SSE4a/BMI e os 58.984 inícios de função continuam presentes.

O watchdog também passou a registrar GPRs e os bits baixos de XMM0–7 a partir
do contexto interrompido, sem conversão de ponto flutuante no handler. Os
diagnósticos anteriores de SIGILL/SIGSEGV foram mantidos.

## Verificações e limite atual

`bash build.sh --test` passou **11/11** antes e depois da correção. Foram
acrescentadas verificações dentro dos grupos existentes:

- 512 comparações do trampoline RDTSC com um callee System V que destrói
  todos os registradores voláteis e YMMs: GPRs, flags, vetores e red zone preservados;
- imports de TSC com frequência de 1 GHz e valores delimitados pelo mesmo
  `CLOCK_MONOTONIC`, migrando por todos os CPUs permitidos;
- validação dos patches na imagem preparada real, sem executar seus módulos.

A primeira compilação do novo teste usou um método inexistente nesta versão
do Xbyak (`getMaxSize`); foi corrigido para o tamanho efetivamente alocado. O
log da tentativa falha foi preservado e não houve restauração de fontes.

Os avisos de permutações conflitantes do cache levam ao descarte da entrada
de preload e à compilação em runtime (`vk_pipeline_serialization.cpp`). Isso
não explica o laço da thread principal. Os caches foram preservados; não se
declara que todos os avisos do recompilador sejam irrelevantes ao gameplay.

**Ainda não há confirmação de um quadro real após a correção.** Esta sessão
roda num sandbox sem `/dev/dri` e com `ptrace` bloqueado. A tentativa completa
parou no SDL com `No available video device`, antes do motor. O smoke Vulkan
também não enumerou dispositivos. Isso limita a validação gráfica desta
sessão e não indica regressão do RADV no host.

## Captura no ambiente gráfico do host

Os executáveis já estão compilados. Uma captura simples, com pouco impacto
no tempo de execução:

```sh
cd /home/chpub/Projetos/sotc-linux-ivybridge
python3 tools/sotc_render_debug.py \
  --game '/mnt/HD RAID/Jogos/Ports I.A/CUSA08809' --timeout 30 --no-gdb
```

Omitir `--no-gdb` habilita contadores por thread para GNM, filas de comandos,
draws, submissões Vulkan, flips, apresentação e tentativas de sinalização.
No watchdog, o GDB captura pilhas, filas e os operandos do temporizador,
validando a assinatura de código antes de usar offsets específicos.
Breakpoints alteram o tempo de execução: comparar com a captura simples.

Cada execução cria `out/logs/render-<UTC>-<pid>/`, com `game.log`, argumentos,
hashes dos binários, diff, mapas e amostras de threads. Usa os artefatos de
preparação existentes; não roda novamente os scripts de preparação. Não limpa
caches nem sobrescreve logs antigos. O trigger de screenshot solicita três
quadros pelo caminho de captura já existente, em `user/screenshots/`.
Uma chamada ao presenter ou uma imagem preta não comprova renderização do jogo.

Próxima verificação: confirmar que a thread principal saiu do laço, conferir
submissões/flips e inspecionar as capturas de quadros reais. Depois, verificar
continuidade e entrada. FPS, resolução final e artefatos Polaris continuam pendentes.
