# Testes de emulação no Linux Ivy Bridge

Base: 0.60.6-plus1, branch `linux-ivybridge`. Os testes usam os geradores e os
patches existentes em `gpu/sotc/`, sem carregar imagens comerciais ou iniciar o jogo.

## Executar

Com o ambiente da etapa 1 já preparado:

~~~sh
bash build.sh --test
LD_BIND_NOW=1 out/gpu/cpu-emulation-test
ctest --test-dir out/gpu -R 'ivybridge-build|cpu-emulation|linux-launcher' --output-on-failure
~~~

O build mantém `-march=ivybridge -mno-avx2 -mno-bmi -mno-bmi2 -mno-movbe -mno-lzcnt`,
PGO/LTO desligados e asserções habilitadas nos testes. O alvo de emulação usa
também `-Wall -Wextra -Werror`.

## Referência e cobertura

- `tests/cpu_emulation_reference.h` calcula os resultados por software escalar:
  TZCNT, LZCNT, ANDN, BEXTR, BLSI, BLSMSK, BLSR, MOVBE, EXTRQ, INSERTQ,
  MOVNTSS e MOVNTSD. Não usa intrínsecos das instruções ausentes.
- O harness recebe `State*` em RDI no Linux System V e em RCX no Windows.
  Preserva os registradores da ABI e observa todos os GPRs, todos os YMMs,
  flags definidas, memória, stack e os 128 bytes da red zone.
- Os bytes das instruções originais são somente dados em páginas não executáveis.
  O código realmente executado vem de `EmitCpuEmulationForTest()`. Cada runner
  é decodificado para rejeitar BMI1/BMI2/AVX2/MOVBE/LZCNT/SSE4a nativos.
- Inclui zero, todos os bits ligados, padrões alternados, cada posição de bit,
  64 combinações das flags aritméticas e entradas aleatórias de seed fixa.
  Leituras/escritas de 16/32/64 bits conferem preservação parcial e zero-extension.
- Inclui destino igual à fonte, destino igual ao controle, todos iguais,
  RCX usado pelos shifts e registradores altos; destino igual à base/índice
  de um operando de memória também é coberto.
- Memória: alinhada, desalinhada, deslocamento negativo, índice escalado,
  RSP positivo, red zone e RIP relativo abaixo de 2 GiB. A última leitura/escrita
  de cada largura termina antes de uma página inacessível; canários detectam
  alterações fora do operando.
- BEXTR percorre todos os 65.536 controles de 16 bits em seis formas selecionadas.
  EXTRQ/INSERTQ de registrador percorrem todos os pares definidos de comprimento
  e índice. Campos zero e bits altos ignorados também são verificados.
- Flags e partes do resultado indefinidas pela arquitetura ficam fora da comparação.
  Em particular, SSE4a não define XMM[127:64] nem resultados com índice + comprimento
  maior que 64. Isso não permite destruir YMM[255:128].
- Os stores MOVNT usam a reescrita existente para MOVSS/MOVSD. O helper de testes
  não copia suas formas RIP-relativas: a reescrita real ocorre no próprio endereço.
- Vetores de resposta fixa validam também os próprios oráculos.

Semântica consultada: [Intel SDM, instruções inteiras e flags](https://cdrdv2-public.intel.com/774492/325383-sdm-vol-2abcd.pdf),
[Clang/LLVM, controles e resultados indefinidos de SSE4a](https://clang.llvm.org/doxygen/ammintrin_8h.html)
e [Intel, preservação de YMM nas instruções SSE legadas](https://www.intel.com/content/dam/develop/external/us/en/documents/319433-024-697869.pdf).

## Falha corrigida e validação em 23/10/2026

A primeira rodada encontrou corrupção em todas as 270 formas EXTRQ/INSERTQ:
o writeback com `VMOVQ` zerava YMM[255:128]. Os quatro writebacks passaram a usar
`MOVQ` legado. A mudança preserva os bits superiores sem introduzir ISA ausente.
Os cálculos BMI1/MOVBE/LZCNT não precisaram de alterações.

Validação no Intel Core i7-3770:

- **1.276 formas, 2.766.048 comparações por software, todas aprovadas**.
- `bash build.sh --test`: **9/9 grupos CTest aprovados**, incluindo a emulação,
  auditoria de ISA e seis casos do launcher/ELF/bloqueio de CPU.
- Também corrigidos os símbolos de runtime ausentes nas fixtures C++ e a largura
  de `runtime_disabled_optimizations`, que é `uint64_t` na biblioteca.

Logs locais ignorados pelo Git: `out/cpu-emulation-first-run.log` (falha reproduzida),
`out/cpu-emulation-build.log`, `out/cpu-emulation-test.log`, `out/tests.log`.
Nenhum binário, log, pacote extraído ou alteração de submódulo integra os commits.

## Limite desta validação

O loader continua rejeitando o carregamento de imagens nesta CPU. Os testes
unitários não comprovam a integração do scanner, dos trampolins e dos sinais no
loader Linux. Não foram executados o jogo, testes visuais ou medições de FPS.
O caminho Windows foi preservado no harness, mas não foi executado nesta máquina.

## Primeiro passo de separação do scanner

Após aprovar os oráculos, os helpers puros foram extraídos para
`gpu/sotc/cpu_patch_decode.{h,cpp}`: decodificação limitada pelo tamanho disponível,
identificação dos aliases de RSP, classificação de terminadores e cálculo de
destinos relativos. O scanner Windows usa esses mesmos helpers. A travessia de
funções, análise da red zone, reconhecimento de tabelas de salto, geração e
instalação de trampolins permanecem na implementação existente.

`cpu-patch-decode-test` vincula apenas Zydis/Zycore e fmt, além das bibliotecas
básicas C/C++. Não depende do renderer ou do runtime. Foram aprovados 24 encodings
e 85 janelas truncadas, inclusive antes de uma página protegida, saltos relativos
positivos/negativos e seus extremos, calls, condicionais, saltos indiretos, RET,
INT3, UD2, SYSRET, operandos RIP e aliases de RSP. Os bytes nunca são executados.

Validação final após a extração:

- `LD_BIND_NOW=1 bash build.sh --test`: **10/10 grupos CTest aprovados**.
- Emulação: permanecem **1.276 formas e 2.766.048 comparações aprovadas**.
- Auditoria: **272 comandos de compilação**, duas configurações de ISA, todos
  com Ivy Bridge e PGO/LTO desligados.
- Python: **52/52 aprovados, zero skips**, executando os módulos existentes
  exceto `test_probe.py`. Os 14 casos desse módulo dependem de passar pelo
  bloqueio de CPU do loader e continuam fora desta rodada.
- Conferidos por comparação com a etapa 1: `src/probe.c`, a ponte
  `sotc_patches.cpp` e todos os fontes do renderer/recompilador estão inalterados.

O próximo bloqueio é compartilhar a travessia completa e o tratamento das formas
curtas, além de integrar os fallbacks Linux com `ucontext`, `SIGILL` e pilhas de
sinais por thread. Essa extração não altera os stubs de detecção no Linux nem
habilita o carregamento de imagens nessa CPU.

Logs adicionais: `out/cpu-scanner-build.log`, `out/cpu-scanner-test.log` e
`out/cpu-stage-python-tests.log`. Os commits desta tarefa usam a autoria técnica
local `Codex <codex@localhost>`, definida somente nos comandos Git.

## Arquivos desta evolução, depois do checkpoint da etapa 1

- `.gitattributes` (preservação do CRLF do header existente)
- `build.sh`
- `docs/sotc/LINUX-CPU-TESTS.md`
- `docs/sotc/LINUX-IVYBRIDGE.md`
- `gpu/CMakeLists.txt`
- `gpu/sotc/cpu_patch_decode.cpp`
- `gpu/sotc/cpu_patch_decode.h`
- `gpu/sotc/cpu_patches.cpp`
- `gpu/sotc/cpu_patches.h`
- `tests/cpu_emulation_reference.h`
- `tests/test_cpu_emulation.cpp`
- `tests/test_cpu_patch_decode.cpp`
- `tests/test_gpu_runtime_stubs.cpp`
