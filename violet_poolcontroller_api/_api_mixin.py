"""Internal interface shared by API domain mixins."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping


class APIClientMixin:
    """Define core operations consumed by domain-specific API mixins."""

    _dosing_standalone: bool

    async def _request(
        self,
        endpoint: str,
        *,
        method: str = "GET",
        params: Mapping[str, Any] | None = None,
        query: str | None = None,
        json_payload: Any | None = None,
        data: Any | None = None,
        expect_json: bool = False,
        priority: int = 3,
        retryable: bool | None = None,
    ) -> Any:
        raise NotImplementedError

    async def _request_json_dict(
        self,
        endpoint: str,
        *,
        params: Mapping[str, Any] | None = None,
        query: str | None = None,
        payload_name: str,
    ) -> dict[str, Any]:
        raise NotImplementedError

    async def set_config(self, config: Mapping[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    async def set_target_value(self, key: str, value: float) -> dict[str, Any]:
        raise NotImplementedError

    async def set_switch_state(
        self,
        key: str,
        action: str,
        *,
        duration: float | None = None,
        last_value: float | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    async def _trigger_dosing(
        self,
        key: str,
        action: str,
        *,
        duration: float | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    def _build_manual_command(
        self,
        key: str,
        action: str,
        *,
        duration: float | None = None,
        last_value: float | None = None,
    ) -> str:
        raise NotImplementedError

    def _is_base_module_function(self, key: str) -> bool:
        raise NotImplementedError

    @staticmethod
    def _csv_query_from_values(values: Iterable[str], *, field_name: str) -> str:
        raise NotImplementedError

    @staticmethod
    def _command_result(body: str | dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError
