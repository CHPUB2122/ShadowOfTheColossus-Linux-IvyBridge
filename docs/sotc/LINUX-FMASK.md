# Gráficos: FMASK e layouts de permutações — 24/10/2026

Esta etapa trata apenas de correção gráfica. Não altera resolução, efeitos,
qualidade, threads de produção, parâmetros de desempenho, launcher, saves ou CPU.
**Resultado posterior no host: o defeito visual principal persistiu.** O usuário
confirmou a biblioteca `graphics-layout` em `/proc/PID/maps`; os três PNGs em
`out/graphics-layout/user/screenshots/` mostram Wander magenta e Agro alternando.
As correções abaixo não são explicação suficiente dos pixels incorretos.
Próximo teste único: [captura e histórico de pixel](LINUX-PIXEL-CAPTURE.md).
Não há `/dev/dri` neste ambiente.

## Baseline oficial preservado

Execução real confirmada pelo usuário:
`out/logs/play-20261024T175323Z-9975/`, saída 0 após 147,96 s.
O ambiente é produção, quatro diagnósticos principais em 0, CP/recorder em 1.
`./run.sh --dry-run` confirmou os mesmos artefatos e configuração. Não foi
repetida uma tentativa de gameplay sem dispositivo de vídeo.

Os três arquivos mencionados em `/mnt/data` não estão montados nesta sessão.
O run equivalente foi encontrado no repositório: registra os 15,3 FPS/2773 MB
relatados. Esses números identificam a execução; não foram usados para otimizar.
`user/screenshots` está vazio; não se inventou comparação visual com os hashes
das capturas históricas.

Backup integral anterior às mudanças gráficas:
`/home/chpub/Projetos/.sotc-backups/graphics-20261024T180219Z/`.
São **39.262 arquivos verificados, zero divergências**, incluindo working tree,
Git/submódulos, artefatos, evidências, caches e saves.

Evidências desta etapa:
`out/logs/graphics-fmask-20261024T180929Z/`.

## Primeira divergência comprovada: FMASK gera um vetor menor

`resource_patching_pass.cpp` substituía leituras/amostragens FMASK de tipo
`F32x4` por `F32x2`, com os bits `0x76543210` e `0xfedcba98`. São exatamente as
duas constantes do módulo inválido `0xdf2d1d0b_0.spv`, interpretadas como floats
aproximadamente `1.076e33` e `-1.467e38`. Ele lê o índice 2 desse vetor em três
pontos; o validador confirma o erro.

Um fixture com o passe e o emissor reais reproduziu o defeito sem GPU:

| Caminho | Biblioteca original | Variante corrigida |
| --- | --- | --- |
| ImageRead FMASK, lendo RGBA | SPIR-V inválido: índice 2 em vec2 | SPIR-V válido, vec4 |
| ImageSampleRaw FMASK, lendo RGBA | mesmo erro | SPIR-V válido, vec4 |

XY são preservados bit a bit; Z/W ausentes recebem zero. Essa regra está na
seção de imagens da [ISA GCN da AMD](https://gpuopen.com/download/AMD_GCN3_Instruction_Set_Architecture_rev1.1.pdf).
A exigência de índices constantes válidos está na
[especificação SPIR-V](https://registry.khronos.org/SPIR-V/specs/unified1/SPIRV.html#OpCompositeExtract).
Isso corrige a validade do módulo; isoladamente não comprova a cor correta de
uma textura que tenha sido classificada indevidamente como FMASK.

A varredura somente leitura achou as mesmas constantes também em
`0x949ac65e_0.spv`, que passa no validador, mas usa os valores em multiplicações
de ponto flutuante. Esse shader consta dos traces de gameplay, por exemplo
`render-20261024T145802Z-17201/game.log:4772`. Logo, validar SPIR-V não basta para
excluir contaminação de cor.

## Divergência mais forte: o binário e sua análise descrevem recursos diferentes

Os metadados foram lidos pela implementação original de `LoadShaderMeta`, usando
a ABI e o schema 21 correspondentes ao cache. O SPIR-V foi inspecionado por
`spirv-dis`. Resultado:

| Shader/permutação | Imagens nos metadados | Imagens no SPIR-V |
| --- | --- | --- |
| `0x949ac65e`, 0 | 12 | 12, com fallback FMASK |
| `0x949ac65e`, 1 | 12 | **14**, sem esse fallback |
| `0xdf2d1d0b`, 0 | 12 | 12, módulo inválido |
| `0xdf2d1d0b`, 1 | 12 | **13**, sem esse fallback |

Em `0x949ac65e_1`, o binário declara `fs_img12` no binding 20, `fs_img13` no 21
e `fs_samp0` no 22. A análise de 12 imagens não corresponde a esse contrato.
O trace recebido também registra `images=12 buffers=8` para esse shader. Essa é
uma divergência concreta entre os recursos que o código espera e os descritos
ao binder; ainda falta pixel history para atribuir um draw a Wander/Agro.

O fonte explica a divergência: ao gerar uma nova permutação, `GetProgram`
compilava `new_info`, mas persistia e retornava `program->info` da primeira
permutação. O caminho assíncrono descartava a análise nova da mesma forma.
Na restauração de cache, todos os módulos voltavam a apontar para a análise do
primeiro módulo carregado. Essa suposição deixa de valer quando a descoberta
de recursos muda, como na transição FMASK/textura normal.

Havia ainda duas lacunas na seleção: contagens de recursos diferentes não eram
rejeitadas antes da comparação; leituras FMASK substituídas por constantes não
eram sempre acompanhadas por uma chave que distinguisse FMASK de textura normal.
Isso permite reutilizar código com uma análise incompatível.

Essa era a hipótese mais forte antes do teste visual: código e descritores de
permutações diferentes. O teste posterior no host manteve o magenta, portanto
não se usa esse defeito como explicação suficiente dos artefatos de gameplay.

## Correções implementadas

- Resultado FMASK mantém quatro componentes, preservando XY e completando Z/W.
- T# FMASK carregado de uma região contígua do flat buffer permanece acompanhado
  pela especialização, mesmo quando a leitura vira uma constante.
- A chave distingue FMASK/textura normal nas duas direções e rejeita contagens
  diferentes de buffers/imagens/samplers.
- Cada nova permutação conserva sua própria análise em memória com endereço
  estável; lookup, bind, tradução assíncrona e serialização usam essa análise.
- O preload conserva a análise de cada permutação, sem substituí-la pela primeira.
- O schema de metadados sobe para 22: os registros 21 podem descrever um layout
  diferente do binário e não são reutilizáveis pela variante corrigida.

O schema novo **não apaga o cache original**. A execução de teste usa sua própria
cópia. Arquivos antigos permanecem nessa cópia, embora não sejam carregados como
metadados 22. Não se alterou `Shader::Profile` nem se chamou reset de cache.

`SOTC_FMASK_TRACE=1` imprime a classificação e os oito dwords do T# durante a
compilação. Fica desligado no uso normal e não acrescenta leitura de memória
guest ou instrumentação por draw. O helper de teste habilita esse trace e o dump
de shaders já existente, preservando os diagnósticos gerais em 0.

## Compilação e validação

Biblioteca corrigida: `out/graphics-layout/libbbgpu.so`.
As **11 unidades afetadas** foram recompiladas com os comandos/flags Ivy Bridge
da configuração CMake existente e ligadas separadamente aos demais objetos
preservados. Os comandos exatos estão em `out/graphics-layout/compile-commands.json`
e `link-command.json`; a compilação não substituiu os binários de produção.

| Verificação | Resultado |
| --- | --- |
| Compilação/link da variante | PASS |
| CTest do baseline | 14/14 |
| Mesma suíte com `LD_LIBRARY_PATH=out/graphics-layout` | 14/14 |
| CTest gráfico isolado, variante completa | 1/1 |
| CTest da correção FMASK isolada | 1/1, antes inválido/depois válido |
| Persistência dos objetos Info entre permutações/reallocação | PASS |
| FMASK → textura normal e direção inversa | PASS |
| Contagens de recursos diferentes com bitset vazio | rejeitadas |
| Roundtrip de análise/especialização e recusa do schema antigo | PASS |
| `spirv-val` dos módulos gerados | PASS |

Logs: `out/graphics-layout/ctest-compatibility.log`, diretórios
`validation-*` das variantes e `ctest-stable.log` no diretório de evidências.
Uma tentativa inicial do fixture usou um singleton ElfInfo privado por causa
das flags de visibilidade; o fixture foi ligado com a visibilidade compartilhada
usada pelos testes de shader existentes. A falha e os resultados finais foram
preservados; não era falha de execução do jogo.

**Os testes não executam Vulkan/RADV nem validam pixels.** A correção não foi
promovida ao renderer normal: `./run.sh` continua usando os mesmos binários
confirmados no host. Não é necessário executar `build.sh` para testar: a variante
já está pronta. Uma compilação futura do código alterado pode incorporar a
correção nos binários normais; aguarda-se a validação visual antes dessa promoção.

## Teste prioritário no host — Fish

As cópias isoladas já estão preparadas. Executar:

```fish
cd /home/chpub/Projetos/sotc-linux-ivybridge
python3 tools/sotc_fmask_test.py --run layout
```

Não há GDB, prazo de sessão, redução de qualidade ou desativação de threads.
O helper usa a mesma imagem/preparação e mantém CP/recorder em 1. O perfil de
teste é `out/graphics-layout/user`; nenhum progresso dele é copiado para o ativo.
A biblioteca é escolhida apenas para esse processo via `LD_LIBRARY_PATH`.

Na mesma cena/câmera da versão normal, comparar:

1. menu como controle; carregar o mesmo progresso;
2. Wander parado e caminhando: alternância verde/magenta/branco entre quadros;
3. Agro parado e cavalgando, incluindo poeira/fumaça;
4. névoa, partículas e pontos luminosos;
5. primeiro colosso: superfícies magenta e materiais/fur;
6. fechamento normal e estabilidade durante a transição menu/mundo.

Para capturar três quadros adjacentes, em outro terminal durante o gameplay:

```fish
cd /home/chpub/Projetos/sotc-linux-ivybridge
python3 tools/sotc_fmask_test.py --capture layout
```

PNGs: `out/graphics-layout/user/screenshots/`.
GCN/SPIR-V recompilados: `out/graphics-layout/user/shader/dumps/`.
O helper imprime o log da sessão em `out/logs/play-...`; o `run.json` contém o
path da biblioteca e o ambiente, e `result.json` registra a saída. O trace
`SOTC FMASK` identifica shader, formato, endereço e T# bruto.

O comando normal permanece:

```fish
cd /home/chpub/Projetos/sotc-linux-ivybridge
./run.sh
```

## Controles discriminatórios opcionais

```fish
python3 tools/sotc_fmask_test.py --run baseline
python3 tools/sotc_fmask_test.py --run recompile
python3 tools/sotc_fmask_test.py --run fixed
```

Executar uma sessão por vez e fechar normalmente entre elas:

- `baseline`: biblioteca original e cópia integral do cache;
- `recompile`: biblioteca original; somente os dois hashes suspeitos são
  recompilados, com os binários anteriores guardados em `quarantine/`;
- `fixed`: mesmo cache do controle anterior, com apenas a correção de tamanho FMASK;
- `layout`: correção completa de layouts/especialização e metadados 22.

Isso separa melhora causada apenas por recompilação da melhora causada pelas
correções. Não reexecutar `--prepare` para restaurar snapshots: o helper recusa
sobrescrever os testes existentes. Todas as sessões usam cópias independentes.

Para repetir verificações locais:

```fish
ctest --test-dir out/graphics-layout --output-on-failure
ctest --test-dir out/graphics-fmask --output-on-failure
```

## Arquivos alterados nesta etapa

1. `gpu/shadps4/shader_recompiler/ir/passes/resource_patching_pass.cpp`
2. `gpu/shadps4/shader_recompiler/specialization.h`
3. `gpu/shadps4/video_core/renderer_vulkan/vk_pipeline_cache.cpp`
4. `gpu/shadps4/video_core/renderer_vulkan/vk_pipeline_cache.h`
5. `gpu/shadps4/video_core/renderer_vulkan/vk_pipeline_serialization.cpp`
6. `tests/test_fmask_shader.cpp` (novo)
7. `tests/test_shader_permutations.cpp` (novo)
8. `tools/sotc_fmask_test.py` (novo)
9. `docs/sotc/LINUX-FMASK.md` (este relatório)

Demais mudanças já existentes não foram atribuídas a esta etapa. O NUL existente
em `vk_pipeline_cache.cpp` foi preservado durante a edição.

Conferência final: **10.335 arquivos protegidos sem alteração**, incluindo
launcher/configuração, binários normais, preparação, CPU/RDTSC/UD2, os dois arquivos
FSR, saves e caches originais. Registro: `preservation-final.json`.

SHA-256 da biblioteca normal preservada:
`dc3a9ef367be7e50935b322ae75c1a4ed53dbe1fa50c42304866d5b9771d80a8`.
Da variante completa:
`d6b26f1cbbe13ae55ca930062965f713f8bb740abb1a6f0ea57a54a68d9498df`.

**Critério de sucesso ainda aberto:** o teste visual posterior no host falhou.
Há defeitos de compilação/associação de recursos comprovados e corrigidos na
variante; não há ainda comparação antes/depois que permita declarar Wander,
Agro, partículas e colosso corrigidos. Não foi feita otimização ou medição nova
de desempenho nesta etapa.
