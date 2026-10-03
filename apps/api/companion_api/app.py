"""FastAPI application factory for companion-api."""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from companion_core.config import AppConfig
from companion_core.errors import CompanionError
from companion_core.ids import new_id
from companion_core.logging import client_id_var, get_logger, request_id_var
from companion_core.version import version_info
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .routes import conversations, health, home, me, memory, settings
from .state import AppState, build_state

log = get_logger("companion_api")


def create_app(cfg: AppConfig, *, state: AppState | None = None, **overrides: Any) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        st = state or build_state(cfg, **overrides)
        app.state.companion = st
        log.info(
            "api ready",
            extra={"llm": st.llm.name, "model": st.llm.model, "home": st.home.name if st.home else "disabled",
                   "vault": getattr(st.vault, "mode", "?"), "clients": len(st.tokens), "warnings": st.warnings},
        )
        if len(st.tokens) == 0:
            log.error("no client tokens configured: every authenticated endpoint will refuse requests (see .env.example)")
        yield
        for closer in (getattr(st.llm, "aclose", None), getattr(st.vault, "aclose", None), getattr(st.home, "aclose", None)):
            if closer:
                await closer()
        st.store.db.close()

    app = FastAPI(title="Companion API", version=version_info("api")["version"] or "0", lifespan=lifespan, docs_url="/docs", redoc_url=None)

    if cfg.api.cors_origins:
        app.add_middleware(
            CORSMiddleware, allow_origins=cfg.api.cors_origins, allow_credentials=False,
            allow_methods=["GET", "POST", "DELETE", "OPTIONS"], allow_headers=["Authorization", "Content-Type", "X-Request-Id"],
            expose_headers=["X-Request-Id"],
        )

    @app.middleware("http")
    async def _request_context(request: Request, call_next):
        rid = request.headers.get("x-request-id") or new_id("req")
        t_rid = request_id_var.set(rid)
        t_cid = client_id_var.set(None)
        started = time.monotonic()
        try:
            response: Response = await call_next(request)
        except Exception:
            log.exception("unhandled error", extra={"path": request.url.path, "method": request.method})
            response = JSONResponse(status_code=500, content={"error": {"code": "internal_error", "message": "internal error", "request_id": rid}})
        finally:
            dur = int((time.monotonic() - started) * 1000)
            request_id_var.reset(t_rid)
            client_id_var.reset(t_cid)
        response.headers["X-Request-Id"] = rid
        if not request.url.path.startswith("/assets"):
            log.info("request", extra={"method": request.method, "path": request.url.path, "status": response.status_code, "ms": dur, "request_id": rid})
        return response

    @app.exception_handler(CompanionError)
    async def _companion_error(request: Request, exc: CompanionError):
        body = exc.to_dict()
        body["request_id"] = request_id_var.get()
        headers = {"WWW-Authenticate": "Bearer"} if exc.http_status == 401 else None
        return JSONResponse(status_code=exc.http_status, content={"error": body}, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        return JSONResponse(status_code=422, content={"error": {"code": "validation_failed", "message": "request validation failed", "details": {"errors": exc.errors()[:10]}, "request_id": request_id_var.get()}})

    @app.exception_handler(HTTPException)
    async def _http(request: Request, exc: HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"error": {"code": "http_error", "message": str(exc.detail), "request_id": request_id_var.get()}}, headers=getattr(exc, "headers", None))

    app.include_router(health.router)
    app.include_router(me.router)
    app.include_router(conversations.router)
    app.include_router(memory.router)
    app.include_router(home.router)
    app.include_router(settings.router)

    dist: Path = cfg.desk_dist_dir
    if cfg.api.serve_desk_ui and (dist / "index.html").is_file():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/", include_in_schema=False)
        async def _index():
            return FileResponse(dist / "index.html", headers={"Cache-Control": "no-cache"})

        for extra in ("favicon.svg", "manifest.webmanifest"):
            if (dist / extra).is_file():
                app.add_api_route(f"/{extra}", (lambda p=dist / extra: (lambda: FileResponse(p)))(), include_in_schema=False)
    else:
        @app.get("/", include_in_schema=False)
        async def _index_missing():
            return JSONResponse({"service": "companion-api", "desk_ui": "not built", "hint": "cd apps/desk && npm ci && npm run build", "docs": "/docs"})

    return app
