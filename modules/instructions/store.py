"""Persistencia de instrucciones en `instructions.json` con escritura atómica.

Invariante: solo UNA instrucción puede estar `active` o `triggered` simultáneamente.
"""
import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import List, Optional

from modules.instructions.models import Instruction

INSTRUCTIONS_PATH = Path(__file__).resolve().parent.parent.parent / "instructions.json"

ACTIVE_STATES = ("active", "triggered")


class InstructionStore:
    _instance: Optional["InstructionStore"] = None
    _init_lock = threading.RLock()

    def __init__(self):
        self._lock = threading.RLock()
        self._items: List[Instruction] = []
        self._load()

    @classmethod
    def get_singleton(cls) -> "InstructionStore":
        with cls._init_lock:
            if cls._instance is None:
                cls._instance = InstructionStore()
            return cls._instance

    def _load(self):
        if not INSTRUCTIONS_PATH.exists():
            return
        try:
            with open(INSTRUCTIONS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._items = [Instruction.from_dict(x) for x in data]
        except Exception:
            self._items = []

    def _save_unlocked(self):
        data = [i.to_dict() for i in self._items]
        fd, tmp = tempfile.mkstemp(
            prefix="instructions.", suffix=".tmp", dir=str(INSTRUCTIONS_PATH.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, INSTRUCTIONS_PATH)
        except Exception:
            try:
                os.unlink(tmp)
            except Exception:
                pass
            raise

    def all(self) -> List[Instruction]:
        with self._lock:
            return list(self._items)

    def get(self, instruction_id: str) -> Optional[Instruction]:
        with self._lock:
            for i in self._items:
                if i.id == instruction_id:
                    return i
        return None

    def get_active(self) -> Optional[Instruction]:
        with self._lock:
            for i in self._items:
                if i.status in ACTIVE_STATES:
                    return i
        return None

    def has_active(self) -> bool:
        return self.get_active() is not None

    def add(self, instruction: Instruction):
        with self._lock:
            instruction.add_history("created", instruction.raw_text)
            self._items.append(instruction)
            self._save_unlocked()

    def set_status(
        self, instruction_id: str, new_status: str, reason: str = ""
    ) -> Optional[Instruction]:
        with self._lock:
            inst = next((i for i in self._items if i.id == instruction_id), None)
            if not inst:
                return None
            old = inst.status
            inst.status = new_status
            inst.add_history(f"status:{old}->{new_status}", reason)
            self._save_unlocked()
            return inst

    def mark_entered(self, instruction_id: str, details: str = ""):
        with self._lock:
            inst = next((i for i in self._items if i.id == instruction_id), None)
            if not inst:
                return
            inst.entered = True
            inst.status = "triggered"
            for c in inst.entry_conditions:
                if c.fired_at == 0.0:
                    c.fired_at = time.time()
            inst.add_history("entry_fired", details)
            self._save_unlocked()

    def mark_exited(self, instruction_id: str, details: str = ""):
        with self._lock:
            inst = next((i for i in self._items if i.id == instruction_id), None)
            if not inst:
                return
            inst.exited = True
            inst.status = "completed"
            for c in inst.exit_conditions:
                if c.fired_at == 0.0:
                    c.fired_at = time.time()
            inst.add_history("exit_fired", details)
            self._save_unlocked()

    def expire_check(self, now: Optional[float] = None) -> List[str]:
        """Marca como `expired` las instrucciones cuya TTL pasó. Retorna IDs afectados."""
        now = now or time.time()
        expired_ids = []
        with self._lock:
            for inst in self._items:
                if (
                    inst.status in ACTIVE_STATES
                    and inst.expires_at > 0
                    and now >= inst.expires_at
                ):
                    inst.status = "expired"
                    inst.add_history("expired", "TTL alcanzada")
                    expired_ids.append(inst.id)
            if expired_ids:
                self._save_unlocked()
        return expired_ids
