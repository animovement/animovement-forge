# animovement-forge

Conda recipes for the [animovement](https://animovement.dev) R package ecosystem, published to the [animovement](https://prefix.dev/channels/animovement) channel on prefix.dev.

## Install

```bash
pixi add --channel https://prefix.dev/animovement --channel conda-forge r-animovement
```

Or to install individual packages:

```bash
pixi add --channel https://prefix.dev/animovement --channel conda-forge r-anicore
```

### Already have R installed?

R also looks in your personal package library (`R_LIBS_USER`, such as
`~/Library/R/x86_64/4.5/library` on macOS), and it looks there before the
environment's own library. If that library holds packages built for the same R
version, the environment's R can load those CRAN builds instead of its conda
ones and crash. We've seen `tidyr` and `vroom` segfault on load this way. To
keep a Pixi environment to its own packages, add this to `pixi.toml`:

```toml
[activation.env]
R_LIBS_USER = "$CONDA_PREFIX/lib/R/library"
```

The optional packages some readers need come from conda too. For HDF5 files
(SLEAP, DeepLabCut), add the bioconda channel and `bioconductor-rhdf5`.

## Packages

| Package | Description |
| --- | --- |
| [r-animovement](recipes/animovement/recipe.yaml) | Toolbox for analysing movement across space and time |
| [r-anicore](recipes/anicore/recipe.yaml) | Core data structures for movement data |
| [r-aniread](recipes/aniread/recipe.yaml) | Reading and writing movement data |
| [r-aniprocess](recipes/aniprocess/recipe.yaml) | Signal processing and filtering of movement data |
| [r-anispace](recipes/anispace/recipe.yaml) | Spatial transformation methods for movement data |
| [r-animetric](recipes/animetric/recipe.yaml) | Calculating movement-based metrics |
| [r-anicheck](recipes/anicheck/recipe.yaml) | Diagnosing movement data quality |
| [r-anivis](recipes/anivis/recipe.yaml) | Visualizing movement data and diagnostics |

## How it works

Versions are tracked via [animovement.r-universe.dev](https://animovement.r-universe.dev), but each recipe builds from the upstream GitHub repo pinned to the exact commit R-Universe built (`context.rev`). Pinning an immutable commit avoids spurious build failures: R-Universe regenerates its `src/contrib` tarballs non-reproducibly, so a pinned `sha256` would go stale within days even at an unchanged version. A nightly CI job checks R-Universe for new versions/commits, updates the pinned `version` and `rev` in the relevant `recipe.yaml` files, commits the changes, and triggers a build and upload to the prefix.dev channel.

To trigger a manual build, use the **Build and Upload** workflow dispatch on GitHub Actions.

## Local development

Requires [pixi](https://pixi.sh).

```bash
# Check for and apply version updates from R-Universe
pixi run python scripts/update-recipes.py

# Build all packages locally (rattler-build resolves order automatically)
pixi run rattler-build build \
  --recipe-dir recipes \
  -c https://prefix.dev/animovement \
  -c conda-forge \
  --output-dir output

# Build a single package
pixi run rattler-build build \
  --recipe recipes/anicore \
  -c https://prefix.dev/animovement \
  -c conda-forge \
  --output-dir output
```
