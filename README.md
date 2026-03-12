# animovement-forge

Conda recipes for the [animovement](https://animovement.dev) R package ecosystem, published to the [animovement](https://prefix.dev/channels/animovement) channel on prefix.dev.

## Install

```bash
pixi add --channel https://prefix.dev/animovement --channel conda-forge r-animovement
```

Or to install individual packages:

```bash
pixi add --channel https://prefix.dev/animovement --channel conda-forge r-aniframe
```

## Packages

| Package | Description |
| --- | --- |
| [r-animovement](recipes/animovement/recipe.yaml) | Toolbox for analysing movement across space and time |
| [r-aniframe](recipes/aniframe/recipe.yaml) | Core data structures for movement data |
| [r-aniread](recipes/aniread/recipe.yaml) | Reading and writing movement data |
| [r-aniprocess](recipes/aniprocess/recipe.yaml) | Signal processing and filtering of movement data |
| [r-anispace](recipes/anispace/recipe.yaml) | Spatial transformation methods for movement data |
| [r-animetric](recipes/animetric/recipe.yaml) | Calculating movement-based metrics |
| [r-anicheck](recipes/anicheck/recipe.yaml) | Diagnosing movement data quality |
| [r-anivis](recipes/anivis/recipe.yaml) | Visualizing movement data and diagnostics |

## How it works

Recipes are sourced from [animovement.r-universe.dev](https://animovement.r-universe.dev). A nightly CI job checks R-Universe for new package versions, updates the pinned version and SHA256 in the relevant `recipe.yaml` files, commits the changes, and triggers a build and upload to the prefix.dev channel.

To trigger a manual build, use the **Build and Upload** workflow dispatch on GitHub Actions.

## Local development

Requires [pixi](https://pixi.sh).

```bash
# Check for and apply version updates from R-Universe
pixi run python scripts/update-recipes.py

# Build a single package locally
pixi run rattler-build build \
  --recipe recipes/aniframe \
  -c https://prefix.dev/animovement \
  -c conda-forge \
  --output-dir output
```
