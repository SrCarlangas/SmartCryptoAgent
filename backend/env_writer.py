"""Escritura segura de .env preservando comentarios y orden.

Uso: `set_env_vars({'PAUSA': '60', 'AGENT_MODE': 'primary'})` reescribe el
archivo línea por línea: si una clave existe la actualiza, si no la añade al
final. Comentarios y líneas en blanco se preservan.
"""
import os
import tempfile
from pathlib import Path
from typing import Dict, Optional

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def _quote(value: str) -> str:
    """Quote value if it contains spaces or special chars."""
    if any(c in value for c in (" ", "#", "$", "\"", "'")) or value == "":
        escaped = value.replace("\\", "\\\\").replace("\"", "\\\"")
        return f'"{escaped}"'
    return value


def _parse_line(line: str) -> Optional[str]:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if "=" not in stripped:
        return None
    return stripped.split("=", 1)[0].strip()


def read_env() -> Dict[str, str]:
    if not ENV_PATH.exists():
        return {}
    out: Dict[str, str] = {}
    with open(ENV_PATH, "r", encoding="utf-8") as f:
        for line in f:
            key = _parse_line(line)
            if key is None:
                continue
            value = line.split("=", 1)[1].strip()
            if value.startswith('"') and value.endswith('"') and len(value) >= 2:
                value = value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
            out[key] = value
    return out


def set_env_vars(updates: Dict[str, str]) -> None:
    """Atomic update: rewrite .env preserving structure, then os.replace."""
    existing_lines = []
    if ENV_PATH.exists():
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            existing_lines = f.readlines()

    seen_keys = set()
    new_lines = []
    for line in existing_lines:
        key = _parse_line(line)
        if key is not None and key in updates:
            new_lines.append(f"{key}={_quote(updates[key])}\n")
            seen_keys.add(key)
        else:
            new_lines.append(line)

    # Append new keys
    for key, value in updates.items():
        if key not in seen_keys:
            if new_lines and not new_lines[-1].endswith("\n"):
                new_lines.append("\n")
            new_lines.append(f"{key}={_quote(value)}\n")

    # Atomic write
    fd, tmp_path = tempfile.mkstemp(
        prefix=".env.", suffix=".tmp", dir=str(ENV_PATH.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp:
            tmp.writelines(new_lines)
        os.replace(tmp_path, ENV_PATH)
    except Exception:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        raise

    # Update os.environ in-process so values that are read fresh take effect
    for key, value in updates.items():
        os.environ[key] = value


def mask_key(key: str, visible: int = 4) -> str:
    if not key:
        return ""
    if len(key) <= visible:
        return "*" * len(key)
    return key[:visible] + "*" * (max(4, len(key) - visible))
