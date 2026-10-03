"""ASGI entry for ``uvicorn companion_api.asgi:app`` (uses COMPANION_CONFIG or the default path)."""

from companion_core.config import load_config
from companion_core.logging import configure_logging

from .app import create_app

_cfg = load_config()
configure_logging(_cfg.logging.level, _cfg.logging.format)
app = create_app(_cfg)
