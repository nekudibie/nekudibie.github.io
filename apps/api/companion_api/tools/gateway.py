"""The tool gateway: the single choke point between any caller (model or router) and actions.

Order of checks for every call: tool exists -> tool enabled -> client permission ->
argument schema (extra fields forbidden) -> resource allowlist -> execute with a
timeout -> audit. The model only ever sees the specs it is permitted to use, but
the checks run even if it names something else.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from companion_contracts.events import ToolCallEvent, ToolResultEvent
from companion_contracts.tools import ToolResult, ToolSpec
from companion_core.auth import ClientIdentity, Permission
from companion_core.errors import CompanionError, PermissionDenied
from companion_core.logging import get_logger
from pydantic import BaseModel, ValidationError

if TYPE_CHECKING:
    from ..state import AppState

log = get_logger(__name__)


@dataclass
class ToolContext:
    identity: ClientIdentity
    state: AppState
    conversation_id: str | None = None
    client_capabilities: list[str] = field(default_factory=list)
    route: str = "llm"


Handler = Callable[[ToolContext, Any], Awaitable[ToolResult]]
ResourceCheck = Callable[[ToolContext, Any], Awaitable[str | None]]  # returns a denial reason or None


@dataclass
class RegisteredTool:
    spec: ToolSpec
    args_model: type[BaseModel]
    handler: Handler
    resource_check: ResourceCheck | None = None
    timeout_s: float = 30.0


@dataclass
class ToolOutcome:
    call_event: ToolCallEvent
    result_event: ToolResultEvent | None
    result: ToolResult | None
    model_content: str  # what goes back to the model as the tool message


class ToolGateway:
    def __init__(self, state: AppState) -> None:
        self.state = state
        self._tools: dict[str, RegisteredTool] = {}

    # -- registration ----------------------------------------------------
    def register(
        self,
        *,
        name: str,
        description: str,
        permission: Permission,
        args_model: type[BaseModel],
        handler: Handler,
        risk: str = "read",
        provider: str | None = None,
        enabled: bool = True,
        disabled_reason: str | None = None,
        resource_check: ResourceCheck | None = None,
        timeout_s: float = 30.0,
        requires_confirmation: bool = False,
    ) -> None:
        schema = args_model.model_json_schema()
        schema.pop("title", None)
        for prop in schema.get("properties", {}).values():
            prop.pop("title", None)
        spec = ToolSpec(
            name=name, description=description, permission=permission.value, risk=risk,  # type: ignore[arg-type]
            parameters=schema, provider=provider, enabled=enabled, disabled_reason=disabled_reason,
            requires_confirmation=requires_confirmation,
        )
        self._tools[name] = RegisteredTool(spec, args_model, handler, resource_check, timeout_s)

    def names(self) -> list[str]:
        return sorted(self._tools)

    def get(self, name: str) -> RegisteredTool | None:
        return self._tools.get(name)

    def specs_for(self, identity: ClientIdentity, *, include_disabled: bool = False) -> list[ToolSpec]:
        out = []
        for t in self._tools.values():
            if not identity.has(Permission(t.spec.permission)):
                continue
            if not t.spec.enabled and not include_disabled:
                continue
            out.append(t.spec)
        return out

    # -- validation ------------------------------------------------------
    def _parse_args(self, raw: Any) -> dict[str, Any]:
        if raw is None:
            return {}
        if isinstance(raw, str):
            raw = raw.strip() or "{}"
            parsed = json.loads(raw)
        else:
            parsed = raw
        if not isinstance(parsed, dict):
            raise ValueError("arguments must be a JSON object")
        return parsed

    async def validate(self, ctx: ToolContext, call_id: str, name: str, raw_args: Any) -> tuple[ToolCallEvent, BaseModel | None, RegisteredTool | None]:
        tool = self._tools.get(name)
        if tool is None:
            return ToolCallEvent(call_id=call_id, name=name, status="unknown_tool", reason=f"no tool named {name!r}"), None, None
        if not tool.spec.enabled:
            return ToolCallEvent(call_id=call_id, name=name, status="denied", reason=tool.spec.disabled_reason or "tool disabled"), None, tool
        if not ctx.identity.has(Permission(tool.spec.permission)):
            return (
                ToolCallEvent(call_id=call_id, name=name, status="denied", reason=f"client {ctx.identity.client_id!r} lacks {tool.spec.permission}"),
                None,
                tool,
            )
        try:
            args = tool.args_model.model_validate(self._parse_args(raw_args))
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            reason = _short_validation_error(exc)
            return ToolCallEvent(call_id=call_id, name=name, status="invalid", reason=reason), None, tool
        if tool.spec.requires_confirmation and ctx.route == "llm":
            return (
                ToolCallEvent(call_id=call_id, name=name, status="needs_confirmation", reason="the user must confirm this on screen", arguments=args.model_dump(mode="json")),
                None,
                tool,
            )
        if tool.resource_check is not None:
            try:
                denial = await tool.resource_check(ctx, args)
            except CompanionError as exc:
                denial = exc.message
            if denial:
                return ToolCallEvent(call_id=call_id, name=name, status="denied", reason=denial, arguments=args.model_dump(mode="json")), None, tool
        return ToolCallEvent(call_id=call_id, name=name, status="validated", arguments=args.model_dump(mode="json")), args, tool

    # -- execution -------------------------------------------------------
    async def call(self, ctx: ToolContext, call_id: str, name: str, raw_args: Any) -> ToolOutcome:
        started = time.monotonic()
        call_event, args, tool = await self.validate(ctx, call_id, name, raw_args)
        if call_event.status != "validated" or args is None or tool is None:
            self._audit(ctx, call_id, name, call_event.status, call_event.reason, raw_args, started)
            payload = json.dumps({"error": call_event.reason, "status": call_event.status, "tool": name})
            return ToolOutcome(call_event, None, None, payload)
        try:
            result: ToolResult = await asyncio.wait_for(tool.handler(ctx, args), timeout=tool.timeout_s)
            status = "ok" if result.ok else "error"
            reason = result.error_code
        except TimeoutError:
            result = ToolResult(ok=False, content=json.dumps({"error": f"{name} timed out after {tool.timeout_s:.0f}s"}), summary=f"{name} timed out", error_code="timeout")
            status, reason = "error", "timeout"
        except PermissionDenied as exc:
            result = ToolResult(ok=False, content=json.dumps({"error": exc.message}), summary=exc.message, error_code=exc.code)
            status, reason = "denied", exc.message
        except CompanionError as exc:
            result = ToolResult(ok=False, content=json.dumps({"error": exc.message, "code": exc.code}), summary=exc.message, error_code=exc.code)
            status, reason = "error", exc.code
        except Exception as exc:  # noqa: BLE001 - last line of defence; details go to the log, not the model
            log.exception("tool crashed", extra={"tool": name})
            result = ToolResult(ok=False, content=json.dumps({"error": f"{name} failed internally"}), summary=f"{name} failed", error_code="internal_error")
            status, reason = "error", exc.__class__.__name__
        self._audit(ctx, call_id, name, status, reason, args.model_dump(mode="json"), started)
        result_event = ToolResultEvent(
            call_id=call_id, name=name, ok=result.ok, summary=result.summary or ("done" if result.ok else "failed"),
            provider=result.provider, is_fixture=result.is_fixture, data=_public_data(result),
        )
        return ToolOutcome(call_event, result_event, result, result.content)

    def _audit(self, ctx: ToolContext, call_id: str, name: str, status: str, reason: str | None, args: Any, started: float) -> None:
        try:
            self.state.store.record_tool_invocation(
                conversation_id=ctx.conversation_id, client_id=ctx.identity.client_id, call_id=call_id,
                tool_name=name, status=status, reason=reason, args=args,
                duration_ms=int((time.monotonic() - started) * 1000), route=ctx.route,
            )
        except Exception:  # noqa: BLE001
            log.exception("could not write tool audit row")
        log.info("tool call", extra={"tool": name, "status": status, "reason": reason, "route": ctx.route})


def _public_data(result: ToolResult) -> dict[str, Any]:
    """Data for the UI: small, no raw private bodies beyond what the tool chose to expose."""
    data = dict(result.data)
    if result.sources:
        data["source_count"] = len(result.sources)
    return data


def _short_validation_error(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        parts = []
        for e in exc.errors()[:4]:
            loc = ".".join(str(x) for x in e.get("loc", ())) or "arguments"
            parts.append(f"{loc}: {e.get('msg')}")
        return "invalid arguments: " + "; ".join(parts)
    return f"invalid arguments: {exc}"
