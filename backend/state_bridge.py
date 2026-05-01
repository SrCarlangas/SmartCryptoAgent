"""BotState singleton: comparte el dict `estado` entre el bot loop y la API.

El bot loop muta `estado` por referencia y persiste con `guardar_estado()`.
La API lee snapshots thread-safe vía `snapshot()`. El RLock protege contra
lecturas inconsistentes durante mutaciones.
"""
import copy
import threading
import time
from typing import Any, Callable, Optional

from backend.ws_manager import ws_manager


class BotState:
    _instance: Optional["BotState"] = None
    _init_lock = threading.RLock()

    def __init__(self, estado: dict):
        self.estado = estado
        self._mutation_lock = threading.RLock()
        self._mode: str = "NORMAL"
        self._active_instruction_id: Optional[str] = None
        self._latest_ctx: dict = {}
        self._started_at: float = time.time()
        self._restart_requested: bool = False
        self._restart_reason: str = ""
        self._restart_requested_at: float = 0.0

    @classmethod
    def initialize(cls, estado: dict) -> "BotState":
        with cls._init_lock:
            if cls._instance is None:
                cls._instance = BotState(estado)
            else:
                cls._instance.estado = estado
            return cls._instance

    @classmethod
    def get(cls) -> "BotState":
        if cls._instance is None:
            raise RuntimeError("BotState no inicializado. Llama initialize() primero.")
        return cls._instance

    @classmethod
    def is_initialized(cls) -> bool:
        return cls._instance is not None

    def update(self, fn: Callable[[], Any]) -> Any:
        with self._mutation_lock:
            return fn()

    def snapshot(self) -> dict:
        with self._mutation_lock:
            return copy.deepcopy(self.estado)

    def set_mode(self, mode: str, instruction_id: Optional[str] = None):
        changed = mode != self._mode or instruction_id != self._active_instruction_id
        self._mode = mode
        self._active_instruction_id = instruction_id
        if changed:
            ws_manager.broadcast_threadsafe(
                "mode_changed",
                {"mode": mode, "active_instruction_id": instruction_id},
            )

    def get_mode(self) -> str:
        return self._mode

    def get_active_instruction_id(self) -> Optional[str]:
        return self._active_instruction_id

    def update_market_snapshot(self, ctx_dict: dict):
        with self._mutation_lock:
            self._latest_ctx = ctx_dict

    def get_market_snapshot(self) -> dict:
        return self._latest_ctx

    def broadcast_tick(self, ctx_dict: dict):
        self.update_market_snapshot(ctx_dict)
        ws_manager.broadcast_threadsafe("tick", ctx_dict)

    def broadcast_trade(self, trade: dict):
        ws_manager.broadcast_threadsafe("trade_executed", trade)

    def broadcast_position_change(self, positions: list):
        ws_manager.broadcast_threadsafe(
            "position_change", {"positions": positions}
        )

    def broadcast_instruction_event(self, event: str, payload: dict):
        ws_manager.broadcast_threadsafe(
            "instruction_event", {"event": event, **payload}
        )

    def uptime_seconds(self) -> float:
        return time.time() - self._started_at

    # ---------- Reinicio programado ----------

    def request_restart(self, reason: str = "config change"):
        """Marca al bot para reiniciarse al inicio del próximo ciclo.
        El reinicio usa os.execv → main() arranca de cero, lo que ejecuta
        cargar_estado + reconciliar_estado automáticamente.
        """
        if not self._restart_requested:
            self._restart_requested = True
            self._restart_reason = reason
            self._restart_requested_at = time.time()
            ws_manager.broadcast_threadsafe(
                "restart_requested",
                {"reason": reason, "requested_at": self._restart_requested_at},
            )

    def is_restart_requested(self) -> bool:
        return self._restart_requested

    def get_restart_info(self) -> dict:
        return {
            "requested": self._restart_requested,
            "reason": self._restart_reason,
            "requested_at": self._restart_requested_at,
        }
