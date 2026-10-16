"""Validate release refs and select GHCR tags. No third-party dependencies."""
import argparse
import json
import re
from pathlib import Path

STABLE = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")


def validate_version(version):
    if len(version) > 128:
        raise ValueError("Version exceeds the Docker tag length limit")
    stable, separator, prerelease = version.partition("-")
    if not STABLE.fullmatch(stable):
        raise ValueError("Expected vMAJOR.MINOR.PATCH, optionally followed by a prerelease")
    if separator:
        identifiers = prerelease.split(".")
        if any(not re.fullmatch(r"[0-9A-Za-z-]+", part) for part in identifiers):
            raise ValueError("Invalid SemVer prerelease")
        if any(part.isdigit() and len(part) > 1 and part.startswith("0") for part in identifiers):
            raise ValueError("Numeric prerelease identifiers must not have leading zeroes")
    return bool(separator)


def metadata(repository, ref, sha):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Invalid owner/repository")
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("Expected a full commit SHA")
    release = ref.startswith("refs/tags/")
    if release:
        tag = ref.removeprefix("refs/tags/")
        if not tag.startswith("v"):
            raise ValueError("Release tags must start with v")
        version = tag[1:]
        prerelease = validate_version(version)
    else:
        if ref != "refs/heads/main" and not re.fullmatch(r"refs/pull/[0-9]+/merge", ref):
            raise ValueError("Only main, pull requests, and version tags are supported")
        version, prerelease = "sha-" + sha[:12], False
    return {
        "image": "ghcr.io/" + repository.lower(),
        "version": version,
        "release": release,
        "prerelease": prerelease,
    }


def select_tags(ref, version, existing, current_main=False):
    """Full release versions are write-once; latest never moves backwards."""
    if ref == "refs/heads/main":
        return [version] + (["edge"] if current_main else [])
    prerelease = validate_version(version)
    if version in existing:
        raise ValueError(f"Image version {version} already exists; choose a new version")
    tags = [version]
    released = [tuple(map(int, tag.split("."))) for tag in existing if STABLE.fullmatch(tag)]
    if not prerelease and (not released or tuple(map(int, version.split("."))) > max(released)):
        tags.append("latest")
    return tags


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--ref", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--existing-tags", type=Path)
    parser.add_argument("--current-main", action="store_true")
    args = parser.parse_args()
    try:
        values = metadata(args.repository, args.ref, args.sha)
        if args.existing_tags:
            existing = json.loads(args.existing_tags.read_text())["Tags"]
            tags = select_tags(args.ref, values["version"], existing or [], args.current_main)
            values["tags"] = ",".join(values["image"] + ":" + tag for tag in tags)
            values["latest"] = "latest" in tags
        for key, value in values.items():
            print(f"{key}={str(value).lower() if isinstance(value, bool) else value}")
    except (ValueError, KeyError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
