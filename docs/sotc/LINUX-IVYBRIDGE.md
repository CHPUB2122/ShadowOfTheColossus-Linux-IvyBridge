# Linux Ivy Bridge — etapa 1 (base 0.60.6-plus1)

Base: `910aff21d1d1f020bba35f0ee57ecac51fe3639c`, branch `linux-ivybridge`.
A referência local `backup/linux-ivybridge-before-stage1` preserva esse commit.
Referência de portabilidade: `linux/linux-port`, commit `6ad9c69`; sem merge completo.

Evolução posterior: [testes de emulação com referências por software](LINUX-CPU-TESTS.md).
As limitações e contagens abaixo registram o checkpoint original da etapa 1;
o alvo de testes CPU agora também funciona na ABI System V do i7-3770.

## Dependências

No CachyOS/Arch, conferir primeiro os pacotes ausentes:

```sh
pacman -Q cmake ninja boost vulkan-headers zydis robin-map
```

Com aprovação do usuário, instalar:

```sh
sudo pacman -S --needed cmake ninja boost vulkan-headers zydis robin-map
```

Bibliotecas já presentes no ambiente analisado: `sdl3`, `fmt`, `xxhash`, `ffmpeg`,
`vulkan-icd-loader`, `vulkan-radeon`, `glslang`, `libx11`. Também são necessários
compiladores C/C++ com C++23, `pkgconf`, Python 3, Git, curl e sha256sum.

VMA não consta dos repositórios configurados. O script abaixo baixa o header MIT
do upstream GPUOpen, versão 3.3.0, para `out/deps`, e confere seu SHA-256:

```sh
bash tools/setup_linux_vma.sh
```

SHA-256 esperado: `90ce12fc4a2466235a09ae02905dd0c13aee80c1bbf11b331ab61230c2ceb112`.
O build usa essa cópia, sem instalar headers no sistema. Os demais submódulos
permanecem nos commits registrados pelo repositório:

```sh
git submodule update --init --recursive
```

Também é possível usar pacotes extraídos sem root: `BB_DEPS_PREFIX` deve apontar
para o prefixo que contém `bin/`, `include/` e `lib/`. O diretório
`out/deps/arch-root/usr`, quando presente, é usado automaticamente. Para reproduzir
essa alternativa no CachyOS/Arch x86-64, sem registrar pacotes no pacman:

```sh
python3 tools/setup_linux_deps.py
bash build.sh --test
```

O manifesto `packaging/linux/ivybridge-deps.lock.json` fixa versões, URLs e SHA-256
extraídos da base local do pacman. São nove pacotes de desenvolvimento/ferramentas,
incluindo as dependências adicionais cppdap, rhash e zycore-c. As bibliotecas básicas
da distribuição continuam sendo usadas do sistema. A extração exige tar com zstd.

Nesta sessão a primeira tentativa com `sudo -n` retornou `a password is required`.
Após autorização e autenticação no prompt do sudo, os seis pacotes do comando
acima foram instalados, mais `cppdap`, `rhash` e `zycore-c`, nas mesmas versões do
manifesto. A compilação validada usou inicialmente as cópias locais verificadas.
Elas continuam disponíveis como alternativa sem root.

## Compilação e verificações

```sh
bash build.sh
bash build.sh --test
python3 -m unittest discover -s tests -p test_linux_launcher.py -v
```

Artefatos: `out/bb-probe`, `out/bb-gpu-capabilities`, `out/gpu/libbbgpu.so`.
O CMake também produz os executáveis em `out/gpu`. O loader exporta os serviços
do runtime usados pela biblioteca compartilhada. O rpath permite iniciar o
loader copiado em `out/` a partir de outro diretório de trabalho.

Todos os fontes C/C++ compilados pelo projeto, incluindo bibliotecas incluídas
e testes, recebem:

```text
-march=ivybridge -mno-avx2 -mno-bmi -mno-bmi2 -mno-movbe -mno-lzcnt
```

PGO e LTO ficam explicitamente desligados no build Linux. AVX permanece permitido.
`BB_JOBS=2` é o paralelismo padrão; pode ser ajustado sem mudar o alvo de CPU.
Bibliotecas do sistema e seus despachos internos de ISA não são recompilados.

Registros gerados:

- `out/gpu-configure.log`: configuração CMake e dependências.
- `out/gpu-build.log`: compilação e ligação.
- `out/gpu/compile_commands.json`: comandos efetivos de compilação, incluindo o runtime C.
- `out/linux-build-info.txt`: commit, submódulos, ferramentas, versões e flags.
- `out/tests-build.log`, `out/tests.log`: testes C/C++ independentes do jogo.
- `out/logs/`: histórico de tentativas e erros, preservado entre builds.

O teste Vulkan existente não usa arquivos comerciais, mas exige acesso à GPU:

```sh
VK_LOADER_LAYERS_DISABLE='~implicit~' out/bb-probe --vulkan-only
```

Essa variável vale somente para o comando. Ela isola as camadas externas da
medição; não altera o driver ou sua configuração persistente.

## Escopo e erros conhecidos

As verificações de CPU do loader e a implementação de emulação foram preservadas.
No i7-3770, carregar uma imagem ainda deve falhar com a mensagem de CPU sem
BMI1/LZCNT/MOVBE. A ativação completa da emulação Linux fica para a etapa seguinte.
O teste `cpu-emulation-test` exige instruções nativas ausentes nessa CPU e uma
adaptação da ABI de seu harness; não integra os testes básicos desta etapa.

Os testes antigos de imagens sintéticas (`tests/test_probe.py`) também passam
pelo mesmo bloqueio de CPU. Não se remove essa verificação para fazê-los passar.

Os alvos antigos `motion-history-test` e `ui-composition-test` referenciam headers
ausentes desta base (`motion_history.h`, `ui_composition.h`). A tentativa de
compilar o primeiro confirmou essa inconsistência. Permanecem `EXCLUDE_FROM_ALL`
e fora da suíte básica; não se recriam componentes de renderização nesta etapa.

Registro inicial de correções:

| Erro | Alteração |
|---|---|
| Bash rejeitava CRLF em `build.sh` | LF e atributo Git para scripts shell |
| CMake/Ninja e headers ausentes | Comando de instalação e prefixo local opcional |
| Xbyak disponível só no ramo Windows | Include compartilhado entre plataformas |
| Zydis exportava dependência `Zycore` sem namespace | Alias para o alvo importado `Zycore::Zycore`, inclusive no prefixo local |
| Contador de divisões de placeholders exportado só no Windows | Exportação Linux retorna zero: essa operação Win32 não ocorre no backend mmap |
| `MAX_PATH` em diagnóstico compilado no Linux | Buffer portátil |
| Lambda misturava `unsigned long` e `unsigned long long` | Retorno explícito `u64` |
| Readbacks misturavam `VAddr` e literais `ULL` em Linux LP64 | Tipo explícito na lambda e em `std::min`, mantendo os mesmos valores |
| Declarações POSIX/GNU ausentes em C11 | Macros de funcionalidades nos alvos/fontes necessários |
| `_DEFAULT_SOURCE` redefinido sob `-Werror` | Definição protegida em `runtime_time.c` |
| Helpers de DLC sem uso no ramo Linux | Compilação dos helpers junto do scanner Windows existente |
| Fixture de controle desatualizada após novos hooks de mouse/eventos | Mouse sem renderer na fixture e ligação com o logger real |
| Testes exigiam rejeição do mesmo NID que já haviam resolvido | Verificação do contrato atual: NIDs válidos e aliases com sufixos resolvem; desconhecidos e tipos incorretos são rejeitados |
| Teste de toque esperava ID zero | Verificar IDs não nulos, distintos e estáveis durante o gesto, conforme a correção já presente no runtime |
| Cópia fixa do nome de fibra com `strncpy` | `memcpy` entre campos de tamanho fixo, conforme `linux/linux-port` |
| Possível truncamento do caminho de atualização | Conferir o comprimento antes da cópia, mantendo `-Werror` |
| Launcher procurava `.exe` e chamava `ctypes.windll` | Seleção de plataforma e flags POSIX |
| DLSS/FSR usavam Win32 incondicionalmente | Carregamento Streamline exclusivo do Windows; captura de entradas preservada; relógio e espera com APIs C++ portáveis |
| Biblioteca GPU usava serviços de heap exclusivos do loader Windows | Adaptação seletiva dos serviços Linux, preservando a interface de múltiplos heaps |

Os hooks de heap não foram validados em gameplay. Pilhas alternativas, fallbacks
completos de sinais/CPU, validação dos shaders e desempenho não são objetivos
de aceitação desta etapa.

O submódulo FSR-Vulkan mantém seu commit original. `build.sh` aplica os dois
patches que já existiam em `gpu/patches/fsr-vulkan`; por isso o working tree desse
submódulo aparece modificado após o build. Não houve atualização de submódulos.

## Resultado da etapa 1 — 23/10/2026

- Gerados `out/bb-probe` (ELF64 x86-64, executável não PIE) e
  `out/gpu/libbbgpu.so` (ELF64 x86-64 compartilhado), com símbolos de depuração.
- Compiladores C/C++: GCC 16.2.1; CMake 4.4.4; Ninja 1.13.2. O FFmpeg 9.0.2
  do sistema compilou e vinculou; reprodução de mídia do jogo não foi testada.
- `bash build.sh --test`: **8/8 grupos CTest passaram**, incluindo auditoria de
  ISA, seis testes do launcher/ELF/bloqueio de CPU, controle SDL virtual, arquivos,
  conteúdo, runtime, semáforos e configurações do upscaler.
- Python adicional: **29/29 testes passaram** (`test_prepare`: 6,
  `test_link_libc`: 7, `test_runtime`: 7, `test_content`: 5, `test_sema`: 4).
- O teste do loader usa `LD_BIND_NOW=1` e outro diretório de trabalho: símbolos
  e biblioteca são resolvidos, e a CPU Ivy Bridge continua sendo rejeitada para
  carregar o jogo, como deve acontecer nesta etapa.
- Teste Vulkan no i7-3770/RX 580 2048SP, RADV Mesa 26.2.4:
  `command submission + 4096-byte readback PASS`.
- O bootstrap local dos nove pacotes foi executado com hashes verificados.
  A repetição de `bash build.sh --test` após reextraí-los passou, com Ninja
  informando `no work to do` tanto para o programa quanto para os testes.
- Após a instalação autorizada, uma configuração CMake nova em
  `out/system-deps-check` encontrou Boost, Vulkan Headers, Zydis/Zycore e robin-map
  em `/usr`. A auditoria de seus 268 comandos também passou. Essa verificação foi
  de configuração; os binários validados acima foram construídos com o prefixo local.
- `bash -n`, sintaxe Python e `git diff --check` passaram. Os fontes
  `gpu/sotc/*` permanecem idênticos ao commit original.

Avisos não fatais dos fontes existentes permanecem nos logs: pragmas/inicialização
do SDK FidelityFX, literal com byte NUL em `vk_pipeline_cache.cpp`, retorno
`nodiscard` e política CMake CMP0218 com o CMake 4.4. Não se alteram algoritmos
de shader para remover esses avisos nesta etapa.

A execução do jogo, a emulação completa no Linux, as pilhas alternativas de
sinais e a validação visual/desempenho continuam pendentes. A suíte completa de
imagens do loader e os antigos testes de renderização não foram declarados aprovados.
Windows não foi recompilado nesta sessão. O checkpoint local da etapa 1 preserva
apenas código, scripts, testes e documentação, sem merge completo ou comandos
Git destrutivos. Binários, logs, dependências extraídas e alterações geradas
no submódulo FSR-Vulkan ficam fora do commit; o build reaplica os patches existentes.

## Verificação antes do commit local

- `bash build.sh --test`: compilação incremental concluída, **8/8 grupos CTest aprovados**.
- `python3 -m unittest discover -s tests -v`: **66 testes executados, 52 aprovados**.
  Os 14 testes de imagens sintéticas em `test_probe.LoaderTests` falharam com
  `This CPU is not supported`, totalizando 20 falhas de asserções, incluindo
  subtestes. Todos pararam na verificação de CPU preservada; não houve testes
  ignorados. A suíte Python completa continua sem aprovação nesta CPU.
- Teste Vulkan existente: **command submission + 4096-byte readback PASS**
  na RX 580 2048SP com RADV, usando `LD_BIND_NOW=1`.
- Sintaxe shell/Python e `git diff --check` aprovados. Conferidos também:
  função `require_cpu_features()` e fontes `gpu/sotc/*` idênticos à base,
  ramo Windows de `build.sh` idêntico após normalizar CRLF, e os dois patches
  preexistentes aplicados ao submódulo, sem mudar sua revisão.

O log completo da descoberta Python fica em `out/precommit-python-tests.log`,
ignorado pelo Git. Este é um checkpoint para continuar o desenvolvimento da
etapa 2; não comprova execução do jogo, renderização correta ou a meta de FPS.

## Arquivos alterados

- `.gitattributes`
- `README.md`
- `build.sh`
- `docs/sotc/LINUX-IVYBRIDGE.md`
- `gpu/CMakeLists.txt`
- `gpu/shadps4/video_core/buffer_cache/buffer_cache.cpp`
- `gpu/shadps4/video_core/page_manager.cpp`
- `gpu/shadps4/video_core/renderer_vulkan/vk_dlssg.cpp`
- `gpu/shadps4/video_core/renderer_vulkan/vk_framegen.cpp`
- `gpu/shadps4/video_core/renderer_vulkan/vk_fsrfg.cpp`
- `gpu/shadps4/video_core/renderer_vulkan/vk_rasterizer.cpp`
- `packaging/linux/ivybridge-deps.lock.json`
- `sotc.py`
- `src/probe.c`
- `src/runtime_content.c`
- `src/runtime_fiber.c`
- `src/runtime_file.c`
- `src/runtime_memory.c`
- `src/runtime_sotc.c`
- `src/runtime_time.c`
- `tests/test_content.c`
- `tests/test_linux_launcher.py`
- `tests/test_pad.c`
- `tests/test_runtime.c`
- `tests/test_runtime_host.c`
- `tests/test_sema.c`
- `tools/check_linux_build.py`
- `tools/setup_linux_deps.py`
- `tools/setup_linux_vma.sh`

No submódulo FSR-Vulkan, os patches preexistentes alteram `src/ffx_vk_fsr4_v07.c`
e `upstream/ffx-1.1.4/sdk/src/backends/vk/ffx_vk.cpp`.

O patch completo de fontes desta sessão está em `out/linux-stage1.patch`.
