# violet-poolController-api - API für Violet Pool Controller
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

"""Pytest configuration and fixtures.

Patches ``aiohttp.ClientResponse.__init__`` so that ``aioresponses`` (which has
not caught up with aiohttp 3.14's keyword-only constructor arguments) can still
build mock responses. Without this, tests fail with::

    AttributeError: 'NoneType' object has no attribute 'output_size'

because aiohttp 3.14 dereferences ``stream_writer.output_size`` in ``__init__``
and aioresponses does not pass the new keyword-only args.
"""

from __future__ import annotations

import asyncio
from inspect import signature
from unittest.mock import MagicMock

import aiohttp.client_reqrep
from aiohttp.helpers import TimerNoop

_original_client_response_init = aiohttp.client_reqrep.ClientResponse.__init__

# Required keyword-only args in aiohttp >= 3.14 that aioresponses does not pass.
# Each maps to a sensible default used only when the caller omits it.
_DEFAULT_KWARGS: dict[str, object] = {
    "writer": None,
    "continue100": None,
    "timer": TimerNoop(),
    "request_info": MagicMock(),
    "traces": [],
    "loop": asyncio.new_event_loop(),
    "session": MagicMock(spec=aiohttp.ClientSession),
    # stream_writer must expose .output_size (read in __init__ since 3.14)
    "stream_writer": MagicMock(output_size=0),
}


def _patched_client_response_init(
    self: aiohttp.client_reqrep.ClientResponse,
    *args: object,
    **kwargs: object,
) -> None:
    """Fill in aiohttp 3.14 keyword-only args that aioresponses omits."""
    sig = signature(_original_client_response_init)
    for name, default in _DEFAULT_KWARGS.items():
        if name in sig.parameters and name not in kwargs:
            kwargs[name] = default
    _original_client_response_init(self, *args, **kwargs)


aiohttp.client_reqrep.ClientResponse.__init__ = _patched_client_response_init
