"""Persistencia atómica de parámetros editables en `parameters.json`.

`config.py` lee este archivo al import time para sobrescribir los defaults
hardcoded. Cualquier cambio aquí requiere reinicio del bot para tomar efecto
(el reinicio se programa automáticamente vía `BotState.request_restart()`).
"""
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, Optional

PARAMETERS_PATH = Path(__file__).resolve().parent.parent / "parameters.json"


class ParametersStore:
    _instance: Optional["ParametersStore"] = None
    _init_lock = threading.RLock()

    def __init__(self):
        self._lock = threading.RLock()
        self._values: Dict[str, Any] = {}
        self._load()

    @classmethod
    def get_singleton(cls) -> "ParametersStore":
        with cls._init_lock:
            if cls._instance is None:
                cls._instance = ParametersStore()
            return cls._instance

    def _load(self):
        if not PARAMETERS_PATH.exists():
            return
        try:
            with open(PARAMETERS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self._values = data
        except Exception:
            self._values = {}

    def _save_unlocked(self):
        fd, tmp = tempfile.mkstemp(
            prefix="parameters.", suffix=".tmp", dir=str(PARAMETERS_PATH.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._values, f, ensure_ascii=False, indent=2, sort_keys=True)
            os.replace(tmp, PARAMETERS_PATH)
        except Exception:
            try:
                os.unlink(tmp)
            except Exception:
                pass
            raise

    def all(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._values)

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._values.get(key, default)

    def set(self, key: str, value: Any):
        with self._lock:
            self._values[key] = value
            self._save_unlocked()

    def set_many(self, updates: Dict[str, Any]):
        with self._lock:
            self._values.update(updates)
            self._save_unlocked()

    def reset(self, key: str):
        with self._lock:
            if key in self._values:
                del self._values[key]
                self._save_unlocked()


def load_parameter_overrides() -> Dict[str, Any]:
    """Helper standalone usado por config.py al import time (evita ciclos)."""
    if not PARAMETERS_PATH.exists():
        return {}
    try:
        with open(PARAMETERS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}
