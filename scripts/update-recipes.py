#!/usr/bin/env python3
"""Check R-Universe for new package versions and update recipes accordingly."""

import hashlib
import json
import os
import re
import urllib.request
from pathlib import Path

UNIVERSE_URL = "https://animovement.r-universe.dev"
RECIPES_DIR = Path(__file__).parent.parent / "recipes"


def get_universe_packages() -> dict[str, dict]:
    url = f"{UNIVERSE_URL}/api/packages?fields=Package,Version"
    with urllib.request.urlopen(url) as r:
        data = json.loads(r.read())
    return {pkg["Package"].lower(): pkg for pkg in data}


def get_recipe_version(recipe_path: Path) -> str | None:
    for line in recipe_path.read_text().splitlines():
        line = line.strip()
        if line.startswith("version:") and "${{" not in line:
            return line.split(":", 1)[1].strip().strip('"')
    return None


def compute_sha256(url: str) -> str:
    digest = hashlib.sha256()
    with urllib.request.urlopen(url) as r:
        while chunk := r.read(8192):
            digest.update(chunk)
    return digest.hexdigest()


def update_recipe(recipe_path: Path, package_name: str, new_version: str) -> None:
    tarball_url = f"{UNIVERSE_URL}/src/contrib/{package_name}_{new_version}.tar.gz"
    print(f"  Fetching {tarball_url} ...")
    new_sha256 = compute_sha256(tarball_url)

    content = recipe_path.read_text()
    content = re.sub(
        r'(version:\s*")[^"]+(")',
        rf'\g<1>{new_version}\g<2>',
        content,
        count=1,
    )
    content = re.sub(r'(sha256:\s*)\S+', rf'\g<1>{new_sha256}', content)
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

        universe_version = packages[pkg_name]["Version"]
        original_name = packages[pkg_name]["Package"]
        current_version = get_recipe_version(recipe_path)

        if current_version == universe_version:
            print(f"{pkg_name}: up to date ({current_version})")
        else:
            print(f"{pkg_name}: {current_version} -> {universe_version}")
            update_recipe(recipe_path, original_name, universe_version)
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
