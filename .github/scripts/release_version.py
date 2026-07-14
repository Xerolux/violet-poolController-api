import argparse
import os
import re
import subprocess
from pathlib import Path

Version = tuple[int, int, int]

PROJECT_FILE = Path("pyproject.toml")
PROJECT_VERSION_PATTERN = re.compile(r'(?m)^version\s*=\s*"(\d+)\.(\d+)\.(\d+)"')
STABLE_TAG_PATTERN = re.compile(r"v(\d+)\.(\d+)\.(\d+)")


def _git_output(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _read_current_version() -> Version:
    content = PROJECT_FILE.read_text(encoding="utf-8")
    match = PROJECT_VERSION_PATTERN.search(content)
    if match is None:
        raise SystemExit("Cannot parse version from pyproject.toml")
    return tuple(map(int, match.groups()))


def _read_tags() -> tuple[list[str], list[tuple[Version, str]]]:
    tags = _git_output("tag", "--list").splitlines()
    stable = []
    for tag in tags:
        match = STABLE_TAG_PATTERN.fullmatch(tag)
        if match:
            stable.append((tuple(map(int, match.groups())), tag))
    return tags, stable


def _replace_versions(version: str) -> None:
    project_content, project_count = PROJECT_VERSION_PATTERN.subn(
        f'version = "{version}"',
        PROJECT_FILE.read_text(encoding="utf-8"),
        count=1,
    )
    if project_count != 1:
        raise SystemExit("Could not update pyproject.toml")
    PROJECT_FILE.write_text(project_content, encoding="utf-8")


def _write_outputs(**values: str) -> None:
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
        for key, value in values.items():
            print(f"{key}={value}", file=output)


def _prepare_dev(run_number: int) -> None:
    current = _read_current_version()
    _, stable = _read_tags()
    latest = max(stable, default=((0, 0, 0), ""))
    if current <= latest[0]:
        base = (latest[0][0], latest[0][1], latest[0][2] + 1)
    else:
        base = current

    base_version = ".".join(map(str, base))
    dev_version = f"{base_version}.dev{run_number}"
    dev_tag = f"v{base_version}-dev.{_git_output('rev-parse', '--short', 'HEAD')}"
    _replace_versions(dev_version)
    _write_outputs(
        base_version=base_version,
        dev_version=dev_version,
        dev_tag=dev_tag,
        previous_tag=latest[1],
    )


def _prepare_stable(mode: str, custom: str) -> None:
    current = _read_current_version()
    tags, stable = _read_tags()
    latest = max(stable, default=((0, 0, 0), ""))
    base = max(current, latest[0])

    if mode == "custom":
        match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", custom.strip())
        if match is None:
            raise SystemExit("Custom version must use the X.Y.Z format")
        new = tuple(map(int, match.groups()))
    elif mode == "auto-major":
        new = (base[0] + 1, 0, 0)
    elif mode == "auto-minor":
        new = (base[0], base[1] + 1, 0)
    else:
        new = (base[0], base[1], base[2] + 1)

    if new <= base:
        raise SystemExit("New version must be greater than the current version and tags")

    version = ".".join(map(str, new))
    tag = f"v{version}"
    if tag in tags:
        raise SystemExit(f"Tag {tag} already exists")

    _replace_versions(version)
    _write_outputs(version=version, tag=tag, previous_tag=latest[1])


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    dev_parser = subparsers.add_parser("dev")
    dev_parser.add_argument("--run-number", required=True, type=int)

    stable_parser = subparsers.add_parser("stable")
    stable_parser.add_argument(
        "--mode",
        choices=("auto-patch", "auto-minor", "auto-major", "custom"),
        required=True,
    )
    stable_parser.add_argument("--custom", default="")

    args = parser.parse_args()
    if args.command == "dev":
        _prepare_dev(args.run_number)
    else:
        _prepare_stable(args.mode, args.custom)


if __name__ == "__main__":
    main()
