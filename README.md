# Shadow of the Colossus Remake — Experimental Native Linux Fork

**Status:** Experimental / Alpha / Unfinished  
**Platform:** Linux x86-64, Vulkan  
**Suggested fork release tag:** `v0.60.6-linux-ivybridge-alpha.1`  
**Development baseline:** `0.60.6-plus1` (verify exact Git ancestry before tagging)  
**Original upstream:** [AjncSystem/ShadowOfTheColossus-PC](https://github.com/AjncSystem/ShadowOfTheColossus-PC) — official upstream release `v0.60.6`

> **Important:** This is an experimental, unofficial native Linux adaptation of the Shadow of the Colossus (2018 PS4 remake) PC port. It is not a complete or fully tested release. Major graphics issues were observed on the tested AMD RX 580 2048SP; other GPUs and more powerful systems may behave differently, but artifact-free gameplay has **not** been verified on those systems.

## About

This fork focuses on getting the existing Shadow of the Colossus PC port running **natively on Linux**, including compatibility with older Intel CPUs that lack AVX2 and BMI1.

Development and testing were primarily performed on CachyOS with an Intel Core i7-3770 and an AMD RX 580 2048SP. On this machine, the game launches successfully, reaches the main menu, loads into the open world, and supports exploration, horseback riding and climbing. The first colossus can be reached, although a complete playthrough has **not** been verified.

This repository is being shared as a development snapshot for others who may want to test, improve or continue the Linux port.

## Tested hardware

| Component | Tested configuration |
| --- | --- |
| OS | CachyOS / Arch Linux |
| CPU | Intel Core i7-3770 (Ivy Bridge, no AVX2/BMI1) |
| GPU | AMD Radeon RX 580 2048SP, 8 GB (Polaris / GCN) |
| Driver | Mesa RADV 26.2.4 / Vulkan |
| Memory | 16 GB DDR3 |
| Resolution | 1920 × 1080 |

## GPU compatibility and graphical issues

**Severe graphical artifacts were observed on the RX 580 2048SP used for testing.** Wander, Agro, colossi, fog, smoke and particles can become bright green, magenta, white or otherwise incorrectly shaded; some materials change appearance from frame to frame. Static environments and the main menu generally render better.

These symptoms are consistent with **known, separately reported compatibility problems affecting older AMD GCN/Polaris GPUs** in the upstream PC port:

- [Upstream issue #152 — RX 580 2048SP: flickering entities, smoke and shadows](https://github.com/AjncSystem/ShadowOfTheColossus-PC/issues/152)
- [Upstream issue #158 — RX 570: lighting, particle and shadow artifacts](https://github.com/AjncSystem/ShadowOfTheColossus-PC/issues/158)

**GPU-specific limitation, not a universal compatibility verdict:** The RX 580 is the only GPU on which this Linux fork has been tested. Other systems—especially those using newer GPUs, different architectures, drivers and faster CPUs—**may deliver better performance and may not reproduce the same visual artifacts**. However, this is a possibility, **not a confirmed result**. More powerful hardware alone does not guarantee correct rendering, and this fork has not yet been validated as visually correct on NVIDIA, RDNA or other GPUs.

Community testing across different hardware is welcome.

## Current status

| Feature | Status |
| --- | --- |
| Native Linux startup | Working on tested hardware |
| Main menu | Working; no major visible issues observed |
| World exploration | Working, but graphics severely affected on RX 580 |
| Wander movement, climbing and Agro riding | Working |
| First colossus | Reached; encounter and full playthrough unverified |
| Save/profile handling | Implemented; full checkpoint persistence needs further validation |
| Graphics on RX 580 2048SP | **Severe unresolved artifacts** |
| Performance on test PC | Around 15–17 FPS in observed open-world gameplay, with drops |
| Other GPUs / higher-end PCs | **Not tested; potentially better results** |
| Audio | Incomplete / not fully verified |
| Full-game completion | Not verified |

Observed FPS values are from informal gameplay tests, not a standardized benchmark, and must not be generalized to other hardware.

## Work implemented in this fork

- Native Linux build and runtime integration.
- Compatibility work for older x86-64 processors without AVX2/BMI1.
- BMI1/LZCNT/MOVBE/SSE4a handling, RDTSC timing and UD2/SIGILL fixes.
- Linux startup/launcher fixes, including removal of an unintended short session timeout.
- Shared save-profile resolution, backups and session-locking work.
- Vulkan diagnostics, shader/pipeline tests and RenderDoc capture tooling.
- Experimental FMASK and shader-permutation fixes. These fixed demonstrable compiler/resource issues, **but did not eliminate the graphical artifacts in RX 580 testing**. Experimental variants must not be represented as validated gameplay fixes.

## Running the port

The working development installation on the tested machine starts with:

```bash
./run.sh
```

**Fresh-clone setup has not been independently validated.** The repository must contain the required compiled/prepared artifacts and must be configured with the user's own legally obtained game files. Please consult the Linux development notes in `docs/sotc/` and inspect the build scripts before attempting a new installation.

Do not expect a finished, one-click experience in this alpha snapshot.

## Known limitations

- Unresolved character, colossus, particle and lighting corruption on the tested Polaris GPU.
- Low and inconsistent frame rate on the tested Ivy Bridge + RX 580 system.
- Incomplete or unverified audio functionality.
- Limited test coverage; hardware compatibility cannot yet be guaranteed.
- Building from a fresh clone and completing the entire game have not been verified.

## Credits and origins

- [AjncSystem/ShadowOfTheColossus-PC](https://github.com/AjncSystem/ShadowOfTheColossus-PC) — original unofficial PC port.
- [Lucas-blip-png/ShadowOfTheColossus-PC](https://github.com/Lucas-blip-png/ShadowOfTheColossus-PC) — community compatibility work relevant to older CPUs and AMD GCN.
- The shadPS4, Pink-shadPS4, bloodborne_pc and other upstream contributors whose work is incorporated in the project; preserve their existing notices and commit history.

This Linux adaptation includes AI-assisted development and troubleshooting. The underlying PC port and original game are not creations of this fork.

## License and legal notice

Preserve the upstream **GNU GPL v2** license file, copyright notices, third-party licenses and applicable source-sharing obligations. Refer to the actual source files for any component-specific license terms.

**No commercial game files, PS4 game executables, proprietary firmware/modules, saves, or copyrighted game assets are provided by this repository.** Users must supply any required files from their own legally obtained copies. This project is unofficial and is not affiliated with Sony Interactive Entertainment or Bluepoint Games.

## Development status

**Experimental source release — contributions welcome; active maintenance is not guaranteed.** If you test this fork on another GPU, please include the GPU model, Vulkan driver version, Linux distribution, screenshots, and logs, along with whether graphical artifacts occur.
