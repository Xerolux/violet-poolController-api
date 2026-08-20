# violet-poolController-api - API for Violet Pool Controller
# Copyright (C) 2024-2026  Xerolux
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Everything written into this repository is English.

The policy lives in AGENTS.md; this file is what makes it hold. Two things are
deliberately exempt and must stay exempt: the controller's own error strings in
``const_api.py`` (and the German payloads the mock server replays), which are
data rather than prose, and the German half of the bilingual documentation
under ``docs/de/``.
"""

# ruff: noqa: S101

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
PACKAGE = REPO / "violet_poolcontroller_api"

# Text the controller emits, reproduced verbatim. Translating it would break
# the match with what the device actually says.
#
# Matched by file name, not by path: `python -m build` copies the package into
# `build/lib/`, and an exemption keyed to the original path does not cover the
# copy. That is not hypothetical - it failed the 0.0.38 release job, because
# the release builds the wheel before running the checks.
CONTROLLER_VERBATIM = frozenset({"const_api.py", "mock_server.py"})

# This file has to name the German words it looks for.
SELF = Path(__file__).name

# Directories that hold generated or vendored copies of the sources. Scanning
# them says nothing about what is written in this repository.
GENERATED_DIRS = frozenset({".git", ".tox", ".venv", "venv", "build", "dist", "__pycache__"})

# Words that only appear in German prose. Deliberately not "in", "die" or "der":
# those collide with English or with identifiers.
GERMAN_WORDS = (
    "für",
    "über",
    "nicht",
    "wird",
    "werden",
    "wenn",
    "diese",
    "dieser",
    "keine",
    "sollte",
)
_GERMAN = re.compile(r"\b(" + "|".join(GERMAN_WORDS) + r")\b", re.IGNORECASE)


def _python_sources() -> list[Path]:
    """Return every Python file the policy applies to."""
    return sorted(
        path
        for path in REPO.rglob("*.py")
        if not (GENERATED_DIRS & set(path.parts))
        and not any(part.endswith(".egg-info") for part in path.parts)
        and path.name not in CONTROLLER_VERBATIM
        and path.name != SELF
    )


@pytest.mark.parametrize("path", _python_sources(), ids=lambda p: p.name)
def test_python_sources_are_english(path: Path) -> None:
    """A German comment is read by people who do not speak German."""
    offenders = [
        f"{path.relative_to(REPO)}:{number}: {line.strip()}"
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if _GERMAN.search(line)
    ]

    assert not offenders, "German text outside the exempt files:\n" + "\n".join(offenders)


def test_the_changelog_is_english() -> None:
    """The changelog is what a consumer reads when a version breaks something.

    Code spans are quotations, not prose: an entry that removes a German string
    has to be able to name the string it removed.
    """
    changelog = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    prose = re.sub(r"`[^`]*`", "", changelog)

    offenders = sorted({match.group(0).lower() for match in _GERMAN.finditer(prose)})

    assert not offenders, f"German outside code spans in CHANGELOG.md: {offenders}"


def test_the_controller_strings_stay_german() -> None:
    """The exemption is the point, not an oversight - guard it too.

    If someone "cleans up" the error table into English, the messages stop
    matching what the device reports.
    """
    const_api = (PACKAGE / "const_api.py").read_text(encoding="utf-8")

    assert "Filterdrucküberwachung (Druck zu niedrig)" in const_api


def test_generated_copies_are_not_scanned() -> None:
    """A built wheel is not source, and scanning its copy fails the release.

    `python -m build` writes `build/lib/<package>/`, so the release job runs
    the checks with a duplicate of every module on disk.
    """
    scanned = {path.name for path in _python_sources()}

    assert "const_api.py" not in scanned
    assert not [path for path in _python_sources() if "build" in path.parts]


def test_the_policy_is_written_down() -> None:
    """Without the rule in AGENTS.md this file is just an opinion."""
    agents = (REPO / "AGENTS.md").read_text(encoding="utf-8")

    assert "## Language Policy" in agents
