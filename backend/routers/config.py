"""GET/PUT /api/config — gestión de claves y parámetros del bot."""
import os

from fastapi import APIRouter

from backend.env_writer import mask_key, read_env, set_env_vars
from backend.schemas import (
    ConfigIn,
    ConfigOut,
    ConfigSaveResponse,
    ProviderConfig,
)

router = APIRouter(prefix="/api/config", tags=["config"])

# Keys que requieren reinicio del bot (no son hot-reloadable)
RESTART_KEYS = {
    "BINANCE_API_KEY",
    "BINANCE_SECRET",
    "PROD_MODE",
    "AGENT_MODEL",
    "GOOGLE_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
}


def _build_providers(env: dict) -> list:
    providers = []
    for name, env_key in (
        ("gemini", "GOOGLE_API_KEY"),
        ("claude", "ANTHROPIC_API_KEY"),
        ("openai", "OPENAI_API_KEY"),
    ):
        key = env.get(env_key, "") or os.getenv(env_key, "")
        providers.append(
            ProviderConfig(
                name=name,
                enabled=bool(key),
                key_preview=mask_key(key),
            )
        )
    return providers


def _build_config_out() -> ConfigOut:
    env = read_env()
    # config.py constants are read fresh from os.environ if updated in-process
    pausa = int(env.get("PAUSA", os.getenv("PAUSA", "30")))
    capital_per_slot = float(
        env.get("CAPITAL_PER_SLOT", os.getenv("CAPITAL_PER_SLOT", "650.0"))
    )
    min_position_capital = float(
        env.get("MIN_POSITION_CAPITAL", os.getenv("MIN_POSITION_CAPITAL", "150.0"))
    )
    sell_floor_raw = env.get("SELL_FLOOR") or os.getenv("SELL_FLOOR")
    sell_floor = float(sell_floor_raw) if sell_floor_raw else None

    return ConfigOut(
        prod_mode=env.get("PROD_MODE", "").strip().lower() in ("true", "1", "yes"),
        agent_mode=env.get("AGENT_MODE", os.getenv("AGENT_MODE", "primary")),
        agent_model=env.get("AGENT_MODEL", os.getenv("AGENT_MODEL", "gemini-2.0-flash")),
        pausa=pausa,
        capital_per_slot=capital_per_slot,
        min_position_capital=min_position_capital,
        binance_api_key_preview=mask_key(env.get("BINANCE_API_KEY", "")),
        binance_secret_preview=mask_key(env.get("BINANCE_SECRET", "")),
        providers=_build_providers(env),
        sell_floor=sell_floor,
    )


@router.get("", response_model=ConfigOut)
def get_config():
    return _build_config_out()


@router.put("", response_model=ConfigSaveResponse)
def update_config(body: ConfigIn):
    updates = {}

    if body.prod_mode is not None:
        updates["PROD_MODE"] = "True" if body.prod_mode else ""
    if body.agent_mode is not None:
        updates["AGENT_MODE"] = body.agent_mode
    if body.agent_model is not None:
        updates["AGENT_MODEL"] = body.agent_model
    if body.pausa is not None:
        updates["PAUSA"] = str(int(body.pausa))
    if body.capital_per_slot is not None:
        updates["CAPITAL_PER_SLOT"] = str(float(body.capital_per_slot))
    if body.min_position_capital is not None:
        updates["MIN_POSITION_CAPITAL"] = str(float(body.min_position_capital))
    if body.binance_api_key:
        updates["BINANCE_API_KEY"] = body.binance_api_key
    if body.binance_secret:
        updates["BINANCE_SECRET"] = body.binance_secret
    if body.google_api_key:
        updates["GOOGLE_API_KEY"] = body.google_api_key
    if body.anthropic_api_key:
        updates["ANTHROPIC_API_KEY"] = body.anthropic_api_key
    if body.openai_api_key:
        updates["OPENAI_API_KEY"] = body.openai_api_key

    if not updates:
        return ConfigSaveResponse(
            config=_build_config_out(),
            requires_restart=False,
        )

    set_env_vars(updates)

    restart_keys = [k for k in updates if k in RESTART_KEYS]
    return ConfigSaveResponse(
        config=_build_config_out(),
        requires_restart=bool(restart_keys),
        restart_reason=(
            f"Cambios en {', '.join(restart_keys)} requieren reinicio del bot"
            if restart_keys
            else ""
        ),
    )
