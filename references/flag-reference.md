# Flag reference — the prose behind the usage block

`SKILL.md` lists the flags and the decisions that pick between them. This file explains what the individual quality/output flags actually do, for when a flag's name is not enough.

**Edge feathering** (default on): a hard color-distance cutoff leaves a jagged/staircase boundary wherever the source art had smooth antialiasing, since GIF only supports on/off transparency per pixel. The script instead estimates a continuous alpha in a transition band around the cutoff (color-unmixing against the background), de-fringes those edge pixels, and converts the band to a binary transparent/opaque pattern using a spatially fixed Bayer dither — so the edge reads as soft rather than blocky, without flickering between frames. `--feather-band-multiplier` (default 4.0, i.e. 4x `--tolerance`) widens/narrows the transition band. `--no-feather` only if the user explicitly wants the old hard-cutoff look (e.g. true pixel-art style).

**Crop** (default OFF): standalone `--crop` crops to the transparent bounding box without any other tier step. Any `--compress` tier crops automatically regardless of this flag.

**Output size reporting**: every run prints final dimensions and file size in KB to stderr — use this instead of a separate size check, and as the signal for whether file-size optimization (below) is worth raising.

**Preview contact sheet** (`--preview <path.png>`, off by default): saves a single PNG with evenly-sampled frames composited over a checkerboard, side by side. Pass it on the same run that produces the final GIF.
