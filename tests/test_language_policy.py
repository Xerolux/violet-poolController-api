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
CONTROLLER_VERBATIM = (PACKAGE / "const_api.py", REPO / "tests" / "mock_server.py")

# This file has to name the German words it looks for.
SELF = Path(__file__).resolve()

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
        if ".git" not in path.parts
        and path not in CONTROLLER_VERBATIM
        and path.resolve() != SELF
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
    """The changelog is what a consumer reads when a version breaks something."""
    changelog = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")

    assert not _GERMAN.search(changelog)


def test_the_controller_strings_stay_german() -> None:
    """The exemption is the point, not an oversight - guard it too.

    If someone "cleans up" the error table into English, the messages stop
    matching what the device reports.
    """
    const_api = (PACKAGE / "const_api.py").read_text(encoding="utf-8")

    assert "Filterdrucküberwachung (Druck zu niedrig)" in const_api


def test_the_policy_is_written_down() -> None:
    """Without the rule in AGENTS.md this file is just an opinion."""
    agents = (REPO / "AGENTS.md").read_text(encoding="utf-8")

    assert "## Language Policy" in agents
