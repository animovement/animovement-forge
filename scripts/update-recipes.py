#!/usr/bin/env python3
"""Check R-Universe for new package versions and update recipes accordingly.

Recipes pin the upstream GitHub repo at the exact commit R-Universe built
(`context.rev`). Pinning to an immutable commit -- rather than to a checksum of
R-Universe's `src/contrib` tarball -- avoids spurious build failures: R-Universe
regenerates those tarballs non-reproducibly, so a pinned sha256 goes stale within
days even when the package version is unchanged. A git commit never drifts.
"""

import json
import os
import re
import urllib.request
from pathlib import Path

UNIVERSE_URL = "https://animovement.r-universe.dev"
RECIPES_DIR = Path(__file__).parent.parent / "recipes"


def parse_version(v: str) -> tuple:
    """Best-effort version key for ordering (handles plain X.Y.Z and suffixes)."""
    return tuple(
        (0, int(p)) if p.isdigit() else (1, p)
        for p in re.split(r"[.\-_]", v)
    )


def get_universe_packages() -> dict[str, dict]:
    url = f"{UNIVERSE_URL}/api/packages?fields=Package,Version,RemoteSha,RemoteUrl"
    with urllib.request.urlopen(url) as r:
        data = json.loads(r.read())
    return {pkg["Package"].lower(): pkg for pkg in data}


def get_recipe_field(recipe_path: Path, key: str) -> str | None:
    """Read a value from the recipe's `context` block (e.g. version, rev)."""
    for line in recipe_path.read_text().splitlines():
        line = line.strip()
        if line.startswith(f"{key}:") and "${{" not in line:
            return line.split(":", 1)[1].strip().strip('"')
    return None


def update_recipe(recipe_path: Path, new_version: str, new_rev: str) -> None:
    content = recipe_path.read_text()
    content = re.sub(
        r'(version:\s*")[^"]+(")',
        rf'\g<1>{new_version}\g<2>',
        content,
        count=1,
    )
    content = re.sub(
        r'(rev:\s*)[0-9a-f]{7,40}\b',
        rf'\g<1>{new_rev}',
        content,
        count=1,
    )
    recipe_path.write_text(content)


def main() -> None:
    packages = get_universe_packages()
    updated: list[str] = []

    for recipe_dir in sorted(RECIPES_DIR.iterdir()):
        recipe_path = recipe_dir / "recipe.yaml"
        if not recipe_path.exists():
            continue

        pkg_name = recipe_dir.name
        if pkg_name not in packages:
            print(f"WARNING: {pkg_name} not found in R-Universe, skipping")
            continue

        info = packages[pkg_name]
        universe_version = info["Version"]
        universe_rev = info.get("RemoteSha")
        if not universe_rev:
            print(f"WARNING: {pkg_name} has no RemoteSha in R-Universe, skipping")
            continue

        current_version = get_recipe_field(recipe_path, "version")
        current_rev = get_recipe_field(recipe_path, "rev")

        if current_version == universe_version and current_rev == universe_rev:
            print(f"{pkg_name}: up to date ({current_version} @ {universe_rev[:10]})")
        elif current_version and parse_version(current_version) > parse_version(universe_version):
            # Recipe is pinned ahead of R-Universe (e.g. a version manually
            # bumped straight from GitHub before R-Universe rebuilt it). Don't
            # downgrade -- R-Universe will catch up and match on a later run.
            print(
                f"{pkg_name}: recipe ahead of R-Universe "
                f"({current_version} > {universe_version}), leaving as-is"
            )
        else:
            print(
                f"{pkg_name}: {current_version} @ {(current_rev or '')[:10]} "
                f"-> {universe_version} @ {universe_rev[:10]}"
            )
            update_recipe(recipe_path, universe_version, universe_rev)
            updated.append(pkg_name)

    if "GITHUB_OUTPUT" in os.environ:
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"has_updates={'true' if updated else 'false'}\n")

    if updated:
        print(f"\nUpdated: {', '.join(updated)}")
    else:
        print("\nAll packages are up to date.")


if __name__ == "__main__":
    main()
