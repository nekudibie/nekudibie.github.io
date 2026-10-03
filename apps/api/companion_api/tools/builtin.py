"""Built-in tools for Milestone 1 and 2: memory, clock, home and camera."""

from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from companion_contracts.tools import (
    CameraShowArgs,
    ClockNowArgs,
    HomeControlArgs,
    HomeStateArgs,
    MemoryCorrectArgs,
    MemorySaveArgs,
    MemorySearchArgs,
    ToolResult,
)
from companion_contracts.vault import CorrectionRequest, NoteCreate, SearchRequest
from companion_core.auth import Permission
from companion_core.errors import NotFound, ValidationFailed

from .gateway import ToolContext, ToolGateway


# -- memory ----------------------------------------------------------------------------
async def memory_search(ctx: ToolContext, args: MemorySearchArgs) -> ToolResult:
    req = SearchRequest(query=args.query, limit=args.limit, kinds=args.kinds, scopes=sorted(ctx.identity.memory_scopes))  # type: ignore[arg-type]
    res = await ctx.state.vault.search(req, scopes=ctx.identity.memory_scopes)
    sources = [h.to_source(f"S{i}") for i, h in enumerate(res.hits, start=1)]
    hits_payload = [
        {
            "label": s.label,
            "title": h.title,
            "kind": h.kind,
            "snippet": h.snippet,
            "text": h.text[:600],
            "document_id": h.document_id,
            "chunk_id": h.chunk_id,
            "created_at": h.created_at,
            "source_type": h.provenance.source_type,
            "trust": h.provenance.trust,
            "is_current": h.is_current,
        }
        for h, s in zip(res.hits, sources, strict=True)
    ]
    content = json.dumps({"query": args.query, "count": len(res.hits), "strategy": res.strategy, "hits": hits_payload})
    summary = f"{len(res.hits)} matching record{'s' if len(res.hits) != 1 else ''}" if res.hits else "no matching records"
    return ToolResult(content=content, summary=summary, sources=sources, data={"count": len(res.hits), "strategy": res.strategy}, provider=f"vault:{getattr(ctx.state.vault, 'mode', 'unknown')}")


async def memory_save(ctx: ToolContext, args: MemorySaveArgs) -> ToolResult:
    note = NoteCreate(text=args.text, title=args.title, kind=args.kind, project=args.project)
    doc = await ctx.state.vault.create_note(note, actor=ctx.identity.client_id)
    content = json.dumps({"saved": True, "document_id": doc.id, "title": doc.title, "kind": doc.kind})
    return ToolResult(content=content, summary=f"saved {doc.kind} “{doc.title}”", data={"document_id": doc.id, "title": doc.title, "kind": doc.kind})


async def memory_correct(ctx: ToolContext, args: MemoryCorrectArgs) -> ToolResult:
    doc = await ctx.state.vault.correct(
        args.document_id, CorrectionRequest(new_text=args.new_text, reason=args.reason),
        actor=ctx.identity.client_id, scopes=ctx.identity.memory_scopes,
    )
    content = json.dumps({"corrected": True, "new_document_id": doc.id, "revision": doc.revision, "supersedes": doc.supersedes_id})
    return ToolResult(content=content, summary=f"record updated to revision {doc.revision}", data={"document_id": doc.id, "revision": doc.revision})


# -- clock -----------------------------------------------------------------------------
async def clock_now(ctx: ToolContext, args: ClockNowArgs) -> ToolResult:
    tz = ZoneInfo(ctx.state.config.instance.timezone)
    now: datetime = ctx.state.clock.now().astimezone(tz)
    data = {
        "time_local": now.strftime("%H:%M"),
        "date_local": now.strftime("%A %-d %B %Y"),
        "timezone": ctx.state.config.instance.timezone,
        "iso": now.isoformat(timespec="seconds"),
    }
    return ToolResult(content=json.dumps(data), summary=f"{data['time_local']} {data['date_local']}", data=data)


# -- home ------------------------------------------------------------------------------
async def _home_resource_check(ctx: ToolContext, args: HomeControlArgs) -> str | None:
    access = ctx.state.home_access
    if not access.enabled:
        return "home control is disabled in configuration"
    if not access.is_allowed(ctx.identity, args.entity_id):
        return f"entity {args.entity_id} is not on the allowlist for client {ctx.identity.client_id!r}"
    return None


async def home_control(ctx: ToolContext, args: HomeControlArgs) -> ToolResult:
    provider = ctx.state.home
    assert provider is not None
    params = {k: v for k, v in args.model_dump().items() if k not in {"entity_id", "action"} and v is not None}
    ent = await provider.get_entity(args.entity_id)
    if args.action == "activate" and ent.domain != "scene":
        raise ValidationFailed("activate only applies to scenes")
    if args.action in {"turn_on", "turn_off", "toggle"} and not ent.capabilities.on_off:
        raise ValidationFailed(f"{ent.friendly_name} cannot be switched")
    if "brightness_pct" in params and not ent.capabilities.brightness:
        raise ValidationFailed(f"{ent.friendly_name} does not support brightness")
    res = await provider.call(args.entity_id, args.action, params)
    label = "fixture, not real hardware" if res.is_fixture else res.provider
    verb = {"turn_on": "turned on", "turn_off": "turned off", "toggle": "toggled", "activate": "activated"}[res.action]
    extra = f" at {params['brightness_pct']}%" if "brightness_pct" in params else ""
    summary = f"{ent.friendly_name} {verb}{extra} ({label})"
    content = json.dumps({**res.model_dump(), "friendly_name": ent.friendly_name, "summary": summary})
    return ToolResult(content=content, summary=summary, provider=res.provider, is_fixture=res.is_fixture, data={**res.model_dump(), "friendly_name": ent.friendly_name})


async def home_state(ctx: ToolContext, args: HomeStateArgs) -> ToolResult:
    access = ctx.state.home_access
    if not access.enabled:
        return ToolResult(ok=False, content=json.dumps({"error": "home control is disabled"}), summary="home disabled", error_code="not_configured")
    ents = await access.entities(ctx.identity)
    if args.entity_id:
        ents = [e for e in ents if e.entity_id == args.entity_id]
        if not ents:
            raise NotFound(f"{args.entity_id} is not available to this client")
    if args.domain:
        ents = [e for e in ents if e.domain == args.domain]
    rows = [
        {"entity_id": e.entity_id, "name": e.friendly_name, "state": e.state, "domain": e.domain,
         "brightness": e.attributes.get("brightness"), "unit": e.attributes.get("unit_of_measurement") or e.attributes.get("unit")}
        for e in ents
    ]
    provider = ctx.state.home
    is_fixture = bool(provider and provider.is_fixture)
    return ToolResult(content=json.dumps({"entities": rows, "is_fixture": is_fixture}), summary=f"{len(rows)} entities", provider=provider.name if provider else None, is_fixture=is_fixture, data={"count": len(rows)})


async def camera_show(ctx: ToolContext, args: CameraShowArgs) -> ToolResult:
    access = ctx.state.home_access
    if not access.enabled or ctx.state.home is None:
        return ToolResult(ok=False, content=json.dumps({"error": "no camera provider configured"}), summary="cameras unavailable", error_code="not_configured")
    res = await access.resolve(args.camera, ctx.identity, domains={"camera"})
    if res.entity is None:
        names = [e.friendly_name for e in await access.entities(ctx.identity) if e.domain == "camera"]
        return ToolResult(ok=False, content=json.dumps({"error": f"no camera called {args.camera!r}", "known_cameras": names}), summary="camera not found", error_code="not_found", data={"known_cameras": names})
    view = await ctx.state.home.camera_view(res.entity.entity_id)
    payload = view.model_dump()
    summary = f"showing {view.friendly_name}" + (" (fixture placeholder, not a live feed)" if view.is_fixture else "")
    return ToolResult(
        content=json.dumps({"camera": view.friendly_name, "entity_id": view.entity_id, "is_fixture": view.is_fixture, "stream_kind": view.stream_kind, "note": view.note}),
        summary=summary, provider=view.provider, is_fixture=view.is_fixture, data=payload,
        ui_events=[{"action": "show_camera", "payload": payload}],
    )


def register_builtin(gw: ToolGateway) -> None:
    gw.register(
        name="memory_search", description="Search the user's personal memory vault (notes, decisions, meetings, documents). Returns matching passages with citation labels.",
        permission=Permission.MEMORY_READ, args_model=MemorySearchArgs, handler=memory_search, risk="read",
    )
    gw.register(
        name="memory_save", description="Save something the user explicitly asked to remember (a note, decision, fact or action).",
        permission=Permission.MEMORY_WRITE, args_model=MemorySaveArgs, handler=memory_save, risk="write",
    )
    gw.register(
        name="memory_correct", description="Replace an existing saved record with corrected text, keeping the old revision in history.",
        permission=Permission.MEMORY_WRITE, args_model=MemoryCorrectArgs, handler=memory_correct, risk="write",
    )
    gw.register(name="clock_now", description="Current local date and time.", permission=Permission.CONVERSE, args_model=ClockNowArgs, handler=clock_now)
    home_enabled = gw.state.home is not None
    reason = None if home_enabled else "home.provider is 'disabled' in configuration"
    gw.register(
        name="home_state", description="List the smart-home entities this client may see, with their current state.",
        permission=Permission.HOME_READ, args_model=HomeStateArgs, handler=home_state, enabled=home_enabled, disabled_reason=reason,
        provider=gw.state.home.name if gw.state.home else None,
    )
    gw.register(
        name="home_control", description="Turn an allowed light/switch on or off, set brightness, or activate a scene. Use home_state first to find entity ids.",
        permission=Permission.HOME_CONTROL, args_model=HomeControlArgs, handler=home_control, risk="actuate",
        enabled=home_enabled, disabled_reason=reason, resource_check=_home_resource_check, provider=gw.state.home.name if gw.state.home else None,
    )
    gw.register(
        name="camera_show", description="Show a named camera on the desk screen.",
        permission=Permission.CAMERA_VIEW, args_model=CameraShowArgs, handler=camera_show, enabled=home_enabled, disabled_reason=reason,
        provider=gw.state.home.name if gw.state.home else None,
    )
