# Artefatos verde/magenta: investigação e testes A/B (24/10/2026)

O jogo já renderiza gameplay. Os PNGs da execução
`out/logs/render-20261024T140527Z-11011` mostram o santuário, Wander e Agro,
com materiais verde/magenta e efeitos muito brilhantes sobre um cenário estável.
O print `CUSA08809_20261024_110659_808_game_000027.png` é um exemplo claro.
Há uma hipótese de amplificação por efeitos temporais/bloom, mas ainda não uma
causa demonstrada. Nenhuma correção de cor ou formato foi aplicada por suposição.

Essa execução terminou com código 0 após 263,82 s. A última amostra tem 5.858
apresentações do jogo e 5.858 flips encontrados/consumidos, zero eventos de flip
ausentes, e 244.443 submissões Vulkan concluídas de 244.443 entradas. Portanto,
o diagnóstico atual é de imagem incorreta durante renderização contínua.

## Preservação

Backup anterior às edições:
`/home/chpub/Backups/sotc-artifacts-20261024T142051Z` (`snapshot.tar` e
`manifest.json`, hashes conferidos após gravação). SHA256 de 793 arquivos,
incluindo os fontes CPU/RDTSC/UD2, o submódulo FSR e os arquivos de configuração
e patches preparados, continua igual ao backup. Evidência:
`out/logs/graphics-analysis-20261024T142217Z/preserved-patches.json`.

Os testes abaixo não reparam nem reextraem o jogo. Cada execução gera seu próprio
`cmdline.bin` no diretório novo do diagnóstico e mantém `out/cmdline.bin`,
`out/patches.bin`, patches CPU, caches e dados originais. As configurações de
culling que já estavam na linha de comando continuam presentes.

## Passes encontrados no executável do jogo

Offsets abaixo são relativos à imagem carregada, EU 1.01, não endereços absolutos
do host. A análise usa a imagem já preparada em `out/boot-linked.bin`.

| Caminho | Evidência no código do jogo | Controle de teste |
|---|---|---|
| Motion blur | Condições sobre o campo de settings `+0x390` em `+0xb5164` e `+0xb5bb4` saltam os caminhos de blur quando zero | `r_motionBlurEnable=0` |
| TAA / histórico | Função com rótulo `TemporalAA` em `+0xb6760`; `+0xb6a49` testa `r_aaMethod` (`settings+0x3a8`) antes de habilitar histórico | `r_aaMethod=0` |
| Jitter temporal | `+0xbb96f` testa método e `settings+0x3b0` antes do jitter | `r_aaEnableTemporalProjectMatrixJitter=0` |
| Dither temporal | CVar registrada em `+0x844f6`, valor `settings+0x3b1` | `r_aaEnableTemporalDitherBuffer=0` |
| Bloom | CVars `r_bloomEnable` e `r_bloomEnableFakeBloom`, objetos `+0x2eb8098` e `+0x2eb8218` | Ambos zero |
| Velocity | Alocação nomeada `kRTT_Motion` em `+0x9dad3`; cadeia `kRTT_MotionBlur_Vel`, `MagDepth`, `Tile_Horiz/Vert/Final` em `+0x9e9e0`…`+0x9ec8f` | Mantida; observar formatos e consumidores |
| Saída temporal | `kRTT_TemporalAA_Color_Out_A/B` em `+0x9bda4` / `+0x9be34` | A resolução de cor continua mesmo sem histórico |
| Composição final | `kRTT_PostProcessFinal` em `+0x9c618`; backend possui composição que amostra UI sRGB e cena FP16 antes do VideoOut | Mantida para produzir imagem válida |

As referências dos nomes dos alvos identificam sua criação; não provam sozinhas
qual hash de shader os processa na RX 580. O trace e as diferenças A/B abaixo
servem para estabelecer essa associação durante gameplay.

As opções TAA/motion do antigo código de interface do port não substituem os
controles do motor. O teste usa a linha de comando do próprio jogo. Não são
descartados draws/dispatches arbitrariamente, nem deixados outputs sem produtor.

### Cenário e personagens

O binário contém caminhos diferentes:

- `RenderGBufferBakedPerVertex` / `GBufferAmbientBaked`, referências em
  `+0xc1cfe` e `+0xc1eb9`;
- `RenderGBufferBakedPerProbe` / `GBufferAmbientDynamic`, referências em
  `+0xc1fde` e `+0xc21a7`;
- `ApplyGBufferModifiers` / `BRDFModifyGBuffer`, referências em
  `+0x180348` e `+0x180384`;
- controles de subsurface e probes dinâmicos, além de parâmetros de fur.

Isso fornece caminhos concretos para investigar iluminação/material dinâmico.
Ainda falta associar os draws de Wander/Agro/Mono aos hashes e buffers desses
caminhos. O trace registra VS/FS, MRTs, buffers e texturas para essa comparação.
O perfil `subsurface-off` permite testar separadamente a contribuição subsurface;
ele não desativa toda a iluminação dinâmica.

## Auditoria de formatos e swizzles

Foram inspecionados `regs_color.h`, `liverpool_to_vk.cpp`, `image_view.cpp`,
`vk_pipeline_cache.cpp` e `vk_instance.cpp`:

- R16G16 FLOAT/SNORM/SINT/UINT têm mapeamentos Vulkan distintos e correspondentes.
- O swizzle de exportação do MRT vem de `ColorBuffer::Swizzle()` no pipeline;
  o swizzle da textura amostrada vem de `Image::DstSelect()` na image view.
- As views de storage mantêm componentes identity; sRGB de storage vira UNORM.
- A seleção de formato suportado trata profundidade e alguns formatos sRGB
  pequenos. Não há conversão geral de FP16/SNORM para RGBA8 nesse caminho.
- Existem fallbacks para combinações não implementadas em `SurfaceFormat`.
  O log de gameplay citado não contém `Unknown data_format` desse fallback.
  Avisos de suporte durante enumeração de formatos não identificam um attachment
  efetivamente usado.

Isso não exclui um descriptor errado, alias de imagem ou incompatibilidade de
tipo no shader em execução. Por isso `SOTC_GRAPHICS_DIAG=1` registra, em um quadro
a cada 300 flips, com limite de entradas:

- `TARGETS`: VS/FS, profundidade, formatos GNM brutos/remapeados, conversão,
  exportação, swap, swizzle e formato realmente passado a `vkCreateImageView`;
- `STAGE` / `DISPATCH`: hashes, quantidade de recursos e tamanho do dispatch;
- `TSHARP` / `VIEW`: endereço, tipo numérico, imagem/view real, mapeamento dos
  componentes, mip/layer, storage/target e tamanho;
- `BUFFER`: endereço, tamanho, stride, formato e acesso de cada shader amostrado;
- `MARKER`: rótulos PM4 do jogo, quando emitidos por essa versão.

O primeiro conjunto de recursos de cada shader no quadro amostrado é registrado;
não é uma captura completa de todos os materiais ou draws. Fast binds que
reutilizam recursos podem não passar de novo por `BindTextures`/`BindBuffers`.
A instrumentação não muda formatos, barreiras, shaders ou decisões de execução.

## Executar no host com GPU

Feche qualquer outra instância. Execute uma vez com `baseline` e depois com
`post-off`, usando o mesmo save, local e direção da câmera:

```bash
cd /home/chpub/Projetos/sotc-linux-ivybridge
python3 tools/sotc_render_debug.py --no-gdb \
  --game '/mnt/HD RAID/Jogos/Ports I.A/CUSA08809' \
  --graphics-profile baseline --graphics-diag \
  --timeout 300 --shot-interval 10 --stack-interval 0
```

```bash
python3 tools/sotc_render_debug.py --no-gdb \
  --game '/mnt/HD RAID/Jogos/Ports I.A/CUSA08809' \
  --graphics-profile post-off --graphics-diag \
  --timeout 300 --shot-interval 10 --stack-interval 0
```

Em cada execução, fique parado por alguns segundos perto de Mono e Agro, depois
caminhe com Wander e cavalgue, incluindo movimento lateral e giro de câmera.
Não altere opções gráficas no menu entre as duas execuções. Feche normalmente ao
terminar; código 142 ao alcançar os 300 s significa prazo absoluto do teste,
e deve ser interpretado junto com os contadores, não como prova de deadlock.

`post-off` combina motion blur, histórico/jitter/dither de TAA e bloom desligados.
Os outros perfis são `motion-off`, `temporal-off`, `bloom-off` e
`subsurface-off`: basta substituir o nome no comando. Use os três primeiros
separadamente para descobrir qual contribuição explica uma melhora no combinado.
O produtor do velocity buffer, o G-buffer e a composição final continuam ativos.

Cada teste imprime um diretório `out/logs/render-...` contendo `run.json`,
`game.log`, `result.json`, mapas/tasks e `graphics-cvars.json`. Os PNGs ficam em
`user/screenshots`, com lista e hashes no `result.json`. Execute inicialmente com
`--dry-run` se quiser apenas verificar a preparação sem abrir o jogo.

### Confirmar que o perfil entrou em vigor

`graphics-cvars.json` amostra os valores reais das CVars no processo a cada 5 s,
lendo `/proc/PID/mem`, sem escrever nele. O layout e as instruções de registro
são validados antes de criar o perfil. Confira valores após carregar o save:

- `status: ok` e valores zero nos controles pedidos: perfil observado;
- valor voltou a 1 após menu/load: o jogo sobrescreveu o controle; não considerar
  esse teste como efeito desabilitado;
- `unavailable`, `not-initialized` ou layout incompatível: não há confirmação do
  valor; o motivo permanece no arquivo. Preferir `--no-gdb` para leitura pelo pai.

`result.json` também resume a última amostra em `graphics_profile_check`:
`observed`, `mismatch`, `unconfirmed` ou `baseline`. Isso confirma valores das
CVars de origem; não prova sozinho o conteúdo da cópia de settings de um quadro.

Se só os rastros sumirem, a origem da cor provavelmente antecede o histórico.
Se só o halo diminuir com bloom desligado, procurar a cor/HDR incorreta antes do
bloom. Se os personagens continuarem verde/magenta parados com `post-off`
confirmado, priorizar os G-buffers e o caminho per-probe/material dinâmico.
Essas são regras de interpretação dos próximos resultados, não resultados já
obtidos na RX 580.

## Validação local e limites

Este ambiente não expõe `/dev/dri`; não permite validar aqui a imagem da RX 580.
Compilação final via `bash build.sh --test` aprovada; **11/11 CTest passaram**.
Logs preservados em `out/logs/linux-20261024T143800Z-2/`, com flags Ivy Bridge,
PGO off e LTO off. `git diff --check` não apontou problemas.
O script de validação em
`out/logs/graphics-analysis-20261024T142217Z/validate_graphics_profiles.py`
verificou seis perfis, recusa de versão/layout alterado em sete CVars, recusa de
sobrescrita, preservação dos artefatos preparados e leitura real pai/filho de
valores bool, int zero e float. O dry run do perfil combinado também passou.

As evidências da desmontagem estão em `engine-pass-evidence.txt`,
`pass-label-xrefs.json` e `render-target-xrefs.json` nesse diretório. Os patches
de CPU/RDTSC/UD2 e FSR não foram editados nesta investigação.
