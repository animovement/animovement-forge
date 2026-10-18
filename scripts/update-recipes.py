#!/usr/bin/env python3
"""Check R-Universe for new package versions and update recipes accordingly.

Recipes pin the upstream GitHub repo at the exact commit R-Universe built
(`context.rev`). Pinning to an immutable commit -- rather than to a checksum of
R-Universe's `src/contrib` tarball -- avoids spurious build failures: R-Universe
regenerates those tarballs non-reproducibly, so a pinned sha256 goes stale within
days even when the package version is unchanged. A git commit never drifts.

The `requirements` block is regenerated from the dependencies R-Universe parsed
out of DESCRIPTION at that same commit, so a package can't gain an import (as
aniprocess did with `signal`) without the recipe following.

Finally, each recipe's expected build is looked up on the prefix.dev channel.
Anything missing -- a new version, or one whose last build failed -- sets
`needs_build`, so a failed build is retried the next night instead of being
skipped because the recipes already look up to date.
"""

import json
import os
import re
import urllib.request
from pathlib import Path

UNIVERSE_URL = "https://animovement.r-universe.dev"
CHANNEL_REPODATA_URL = "https://repo.prefix.dev/animovement/noarch/repodata.json"
RECIPES_DIR = Path(__file__).parent.parent / "recipes"

# Shipped with R itself, so there is no conda package to depend on.
BASE_R_PACKAGES = {
    "base", "compiler", "datasets", "graphics", "grDevices", "grid", "methods",
    "parallel", "splines", "stats", "stats4", "tcltk", "tools", "utils",
}


def parse_version(v: str) -> tuple:
    """Best-effort version key for ordering (handles plain X.Y.Z and suffixes)."""
    return tuple(
        (0, int(p)) if p.isdigit() else (1, p)
        for p in re.split(r"[.\-_]", v)
    )


def get_universe_packages() -> dict[str, dict]:
    url = (
        f"{UNIVERSE_URL}/api/packages"
        "?fields=Package,Version,RemoteSha,RemoteUrl,_dependencies"
    )
    with urllib.request.urlopen(url) as r:
        data = json.loads(r.read())
    return {pkg["Package"].lower(): pkg for pkg in data}


def get_channel_files() -> set[str]:
    # prefix.dev answers Python's default User-Agent with a 403.
    req = urllib.request.Request(
        CHANNEL_REPODATA_URL,
        headers={"User-Agent": "animovement-forge", "Cache-Control": "no-cache"},
    )
    with urllib.request.urlopen(req) as r:
        data = json.loads(r.read())
    return set(data.get("packages", {})) | set(data.get("packages.conda", {}))


def get_recipe_field(recipe_path: Path, key: str) -> str | None:
    """Read a value from the recipe's `context` block (e.g. version, rev)."""
    for line in recipe_path.read_text().splitlines():
        line = line.strip()
        if line.startswith(f"{key}:") and "${{" not in line:
            return line.split(":", 1)[1].strip().strip('"')
    return None


def conda_spec(package: str, constraint: str | None) -> str:
    """`dplyr` + `>= 1.1.0` -> `r-dplyr >=1.1.0`; R itself becomes r-base."""
    name = "r-base" if package == "R" else f"r-{package.lower()}"
    if not constraint:
        return name
    op, version = re.match(r"\s*([<>=!]+)\s*(\S+)", constraint).groups()
    # conda versions can't contain "-", which R uses as a separator (1.8-1).
    return f"{name} {op}{version.replace('-', '_')}"


def requirements_from_universe(dependencies: list[dict]) -> tuple[list[str], list[str]]:
    # Keyed by conda name so a package listed under two roles (Imports and
    # LinkingTo, say) appears once, keeping whichever entry has a constraint.
    host: dict[str, str] = {}
    run: dict[str, str] = {}

    def add(specs: dict[str, str], spec: str) -> None:
        name = spec.split()[0]
        if name not in specs or " " not in specs[name]:
            specs[name] = spec

    for role in ("Depends", "Imports", "LinkingTo"):
        for dep in dependencies:
            if dep["role"] != role or dep["package"] in BASE_R_PACKAGES:
                continue
            spec = conda_spec(dep["package"], dep.get("version"))
            add(host, spec)
            # LinkingTo is headers needed at build time only.
            if role != "LinkingTo":
                add(run, spec)
    if "r-base" not in host:
        host = {"r-base": "r-base", **host}
        run = {"r-base": "r-base", **run}
    return list(host.values()), list(run.values())


def normalize_spec(spec: str) -> str:
    """Drop trailing `.0`s so `r-base >=4.1` and `r-base >=4.1.0` compare equal."""
    return re.sub(r"(\d)(?:\.0)+$", r"\1", spec)


def spec_set(specs: list[str]) -> set[str]:
    return {normalize_spec(s) for s in specs}


REQUIREMENTS_RE = re.compile(r"^requirements:\n(?:(?:[ \t].*)?\n)*?(?=^\S)", re.M)


def get_recipe_requirements(content: str) -> tuple[list[str], list[str]]:
    block = REQUIREMENTS_RE.search(content).group(0)
    sections: dict[str, list[str]] = {"host": [], "run": []}
    current = None
    for line in block.splitlines()[1:]:
        if m := re.match(r"  (\w+):\s*$", line):
            current = m.group(1)
        elif (m := re.match(r"\s+- (.+?)\s*$", line)) and current in sections:
            sections[current].append(m.group(1))
    return sections["host"], sections["run"]


def format_requirements(host: list[str], run: list[str]) -> str:
    lines = ["requirements:", "  host:"]
    lines += [f"    - {s}" for s in host]
    lines += ["  run:"]
    lines += [f"    - {s}" for s in run]
    return "\n".join(lines) + "\n\n"


def update_recipe(
    recipe_path: Path,
    new_version: str,
    new_rev: str,
    build_number: int,
    host: list[str],
    run: list[str],
) -> None:
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
    content = re.sub(
        r'^(  number:\s*)\d+',
        rf'\g<1>{build_number}',
        content,
        count=1,
        flags=re.M,
    )
    content = REQUIREMENTS_RE.sub(lambda _: format_requirements(host, run), content, count=1)
    recipe_path.write_text(content)


def is_on_channel(recipe_path: Path, channel_files: set[str]) -> bool:
    content = recipe_path.read_text()
    name = re.search(r"^package:\n\s+name:\s*(\S+)", content, re.M).group(1)
    version = get_recipe_field(recipe_path, "version")
    number = re.search(r"^  number:\s*(\d+)", content, re.M).group(1)
    pattern = re.compile(
        rf"^{re.escape(name)}-{re.escape(version)}-[^-_]+_{number}\.(conda|tar\.bz2)$"
    )
    return any(pattern.match(f) for f in channel_files)


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
        content = recipe_path.read_text()
        current_host, current_run = get_recipe_requirements(content)
        current_number = int(re.search(r"^  number:\s*(\d+)", content, re.M).group(1))

        if current_version and parse_version(current_version) > parse_version(universe_version):
            # Recipe is pinned ahead of R-Universe (e.g. a version manually
            # bumped straight from GitHub before R-Universe rebuilt it). Don't
            # downgrade -- R-Universe will catch up and match on a later run.
            # Its dependencies describe a different commit, so leave those too.
            print(
                f"{pkg_name}: recipe ahead of R-Universe "
                f"({current_version} > {universe_version}), leaving as-is"
            )
            continue

        if "_dependencies" in info:
            host, run = requirements_from_universe(info["_dependencies"])
        else:
            print(f"WARNING: {pkg_name} has no dependency data in R-Universe, keeping requirements")
            host, run = current_host, current_run

        version_changed = current_version != universe_version
        rev_changed = current_rev != universe_rev
        # Order doesn't matter to the solver, so only a different set counts.
        deps_changed = (
            spec_set(host) != spec_set(current_host)
            or spec_set(run) != spec_set(current_run)
        )

        if not (version_changed or rev_changed or deps_changed):
            print(f"{pkg_name}: up to date ({current_version} @ {universe_rev[:10]})")
            continue

        # The upload uses --skip-existing, so a new commit or new dependencies
        # at an unchanged version need a new build number to reach the channel.
        build_number = 0 if version_changed else current_number + 1
        changes = []
        if version_changed or rev_changed:
            changes.append(
                f"{current_version} @ {(current_rev or '')[:10]} "
                f"-> {universe_version} @ {universe_rev[:10]}"
            )
        if deps_changed:
            added = sorted(spec_set(host) - spec_set(current_host))
            removed = sorted(spec_set(current_host) - spec_set(host))
            changes.append(f"requirements +{added} -{removed}")
        changes.append(f"build {current_number} -> {build_number}")
        print(f"{pkg_name}: {'; '.join(changes)}")

        update_recipe(recipe_path, universe_version, universe_rev, build_number, host, run)
        updated.append(pkg_name)

    channel_files = get_channel_files()
    missing = [
        d.name
        for d in sorted(RECIPES_DIR.iterdir())
        if (d / "recipe.yaml").exists() and not is_on_channel(d / "recipe.yaml", channel_files)
    ]

    if "GITHUB_OUTPUT" in os.environ:
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"has_updates={'true' if updated else 'false'}\n")
            f.write(f"needs_build={'true' if missing else 'false'}\n")

    if updated:
        print(f"\nUpdated: {', '.join(updated)}")
    else:
        print("\nAll packages are up to date.")
    if missing:
        print(f"Not yet on the channel: {', '.join(missing)}")
    else:
        print("Every recipe's build is on the channel.")


if __name__ == "__main__":
    main()
