# Wander magenta: um teste de captura no host

## Resultado conhecido e limite da evidência

Os três PNGs `CUSA08809_20261024_155223_{724,811,902}_game_*.png` foram
inspecionados. Wander permanece magenta; no segundo quadro Agro ganha linhas
verdes/magenta que não aparecem da mesma forma nos outros dois. O halo rosa
também está na imagem final. Isso não demonstra se ele nasceu no material,
iluminação ou composição. Nenhum draw de Wander foi identificado com segurança.
Não se atribuiu Wander aos hashes FMASK investigados anteriormente.

O host confirmou `out/graphics-layout/libbbgpu.so` carregada e o defeito persistiu.
Não foi aplicado outro patch de shader ou recursos. **Esta etapa trata somente
de gráficos; não houve otimização de desempenho.**

## Teste preparado

`tools/sotc_pixel_capture.py` lança o mesmo loader e renderer `graphics-layout`
por `renderdoccmd`, com uma cópia verificada do perfil em `out/graphics-pixel/user`.
Não altera o perfil ativo nem o perfil/evidências do teste anterior.
Não há prazo de sessão. Diagnósticos gerais ficam em 0, CP e recorder em 1.
Somente esta sessão usa SDL X11/XWayland e nomes Vulkan para a captura.

O shim atual em `gpu/shim/bbgpu.cpp` implementa os hooks RenderDoc apenas em
Windows; no Linux `TriggerCapture` é vazio. Em vez de alterar/recompilar o
renderer, um pequeno preload separado acessa o RenderDoc já injetado e chama
`TriggerMultiFrameCapture(3)` uma vez por sessão. O próprio RenderDoc delimita
os quadros nos presents; não contamos submissões CP como quadros.

O helper só atua no executável `bb-probe`, com as duas variáveis específicas,
e não carrega RenderDoc por conta própria. A implementação usa a
[API oficial do RenderDoc](https://github.com/baldurk/renderdoc/blob/v1.x/docs/in_application_api.rst)
e a [CLI oficial](https://github.com/baldurk/renderdoc/blob/v1.x/renderdoccmd/renderdoccmd.cpp).
O renderer já nomeia pipelines, módulos com hashes/permutação e recursos.
`SOTC_VK_NAMES=1` habilita esses nomes neste teste. Não se instrumenta cada draw.

## Comandos Fish

Se necessário, instalar apenas a ferramenta de captura disponível no
[pacote renderdoc do Arch](https://archlinux.org/packages/extra/x86_64/renderdoc/):

```fish
sudo pacman -S --needed renderdoc
```

Fechar qualquer execução anterior do jogo. No terminal do desktop do host:

```fish
cd /home/chpub/Projetos/sotc-linux-ivybridge
python3 tools/sotc_pixel_capture.py --run
```

O helper já foi compilado. Se somente os fontes forem transferidos ao host,
compilá-lo antes com `python3 tools/sotc_pixel_capture.py --build`.
Não executar `build.sh` para este teste.

Carregar o mesmo local dos PNGs, deixar Wander e Agro visíveis e parar a câmera.
Confirmar que o magenta ainda ocorre sob a captura. Em outro terminal:

```fish
cd /home/chpub/Projetos/sotc-linux-ivybridge
python3 tools/sotc_pixel_capture.py --capture
```

Esperar os três `.rdc` no diretório `out/graphics-pixel/capture-*/` anunciado,
depois sair normalmente do jogo. O log deve registrar `RenderDoc attached`,
`requested three consecutive presented frames` e três linhas `saved`.
Os PNGs próximos à solicitação ficam em `out/graphics-pixel/user/screenshots/`.
São referência visual da mesma cena, **não correspondência garantida quadro a
quadro** com os RDCs. Não pedir nova captura nesta sessão; limite de três.

Para comparar/voltar ao uso normal, após fechar a sessão de captura:

```fish
cd /home/chpub/Projetos/sotc-linux-ivybridge
./run.sh
```

## O que devolver

- Os três `.rdc` e `capture.json` do diretório anunciado.
- Os três PNGs novos de `out/graphics-pixel/user/screenshots/`.
- `game.log`, `run.json`, `result.json` da sessão `out/logs/play-...` anunciada.
- Informar se o magenta permaneceu com RenderDoc anexado.

Se não gerar RDC, devolver o log; não repetir variantes de efeitos/threads.
O status de saída do wrapper é de `renderdoccmd`: não prova por si só a saída
normal do jogo. O log do loader é necessário para distinguir crash/saída.

## Como a captura discrimina a origem

Abrir os RDCs no qrenderdoc **com o jogo fechado**. Primeiro comparar a imagem
reproduzida no último evento com a imagem vista ao vivo. O histórico da água
(`AGUA.md`) já registra limitações de replay com memória sparse/argumentos
indiretos. Se o replay divergir, seus pixels não servem como prova da causa no
jogo; registrar a divergência e parar esse diagnóstico.

Com replay fiel:

1. Localizar os render targets do G-buffer em Texture Viewer e um pixel interno
   do torso de Wander. Nos PNGs atuais, aproximadamente `(715,640)` em 1920×1080;
   selecionar novamente se câmera/resolução mudarem. Ajustar às dimensões reais
   do target, mip e layer. Evitar bordas/halo/legenda.
2. Usar **Pixel History** nesse target para encontrar a escrita do personagem,
   e confirmar a malha em Mesh Viewer. Um draw final de tela cheia não identifica
   o material. Registrar event ID, nome do pipeline, VS/FS e permutação.
3. No draw identificado, comparar saídas MRT, `shaderOut`, `preMod` e `postMod`
   quando disponíveis; abrir o blend state e os inputs em Pipeline State.
   Conferir recursos, formatos/swizzles, subresources/layouts, samplers, buffers
   e constantes. Não interpretar um canal de G-buffer codificado como RGB final.
4. Se a saída material estiver correta, seguir os consumidores na iluminação e
   composição até a primeira saída divergente. Pixel History não rastreia
   automaticamente dependências entre targets nem resolve toda escrita compute.
5. Comparar o mesmo draw/material no RDC adjacente. Se todos mostram Wander
   errado, usar Agro como comparação temporal; não inventar um quadro correto.

Os scripts existentes `tools/rdoc/rd_hist.py`, `rd_views.py`, `rd_raw.py`,
`rd_flatdump.py`, `rd_spv.py` e `rd_probe.py` ficam disponíveis após obter os
IDs reais. Não foram disparadas varreduras globais de shaders.

## Arquivos e validação local

Novos: `tools/sotc_pixel_capture.py`, `tools/sotc_renderdoc_hook.c`,
`tests/test_pixel_capture.py`, `docs/sotc/LINUX-PIXEL-CAPTURE.md`.
Atualizado: `docs/sotc/LINUX-FMASK.md` para registrar o resultado negativo do host.

Compilado somente `out/graphics-pixel/capture-hook.so`, com flags Ivy Bridge,
sem AVX2/BMI1/BMI2. O teste executa o preload real contra uma API RenderDoc
simulada: três quadros solicitados uma única vez; outro processo ignorado;
ausência de API sem captura/crash. Isso **não valida Vulkan ou replay**.
Resultado local: CTest do helper **1/1** (três casos internos), suíte existente
**14/14**, sintaxe Python/Fish aprovada. Dez hashes protegidos sem alteração,
incluindo ambas as bibliotecas, launcher, loader e arquivos CPU/FSR conferidos.
Logs: `out/graphics-pixel/ctest-capture.log`, `ctest-stable.log` e
`preservation.json`. O preflight também confirmou a ausência de `renderdoccmd`
e recusou iniciar antes de copiar perfis ou executar o jogo.
Comandos de validação:

```fish
ctest --test-dir out/graphics-pixel --output-on-failure
ctest --test-dir out/gpu --output-on-failure
```

Backup desta etapa: `/home/chpub/Projetos/.sotc-backups/pixel-capture-20261024T190359Z/`.
Contém working tree modificado/não rastreado, Git, alterações FSR e PNGs atuais,
complementando o snapshot integral `graphics-20261024T180219Z`. Bibliotecas,
launcher, patches CPU, caches e saves existentes permanecem no lugar.

Sem `/dev/dri` e sem RenderDoc instalado neste ambiente, o próximo passo exige
o host. **A correção dos pixels continua pendente; não houve promoção.**
