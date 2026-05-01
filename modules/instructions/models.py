"""Modelos de datos para instrucciones del usuario al agente."""
import time
import uuid
from dataclasses import dataclass, field
from typing import List, Optional


def _new_id() -> str:
    return f"instr_{uuid.uuid4().hex[:8]}"


@dataclass
class Condition:
    """Condición evaluable cada ciclo del bot."""

    type: str = "price_above"
    # type ∈ {price_above, price_below, rsi_above, rsi_below,
    #         roi_above, roi_below, time_after}
    value: float = 0.0
    operator: str = ">="
    fired_at: float = 0.0


@dataclass
class Action:
    """Acción a ejecutar cuando se cumplen las condiciones."""

    type: str = "BUY"  # BUY | SELL | PARTIAL_SELL
    quantity_btc: float = 0.0
    quantity_usdt: float = 0.0
    sell_pct: float = 1.0
    target_position_id: str = ""  # "any" | id específico


@dataclass
class Instruction:
    id: str = field(default_factory=_new_id)
    raw_text: str = ""
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    complex: bool = False
    status: str = "active"
    # status ∈ {active, triggered, completed, cancelled, failed, expired}
    entry_conditions: List[Condition] = field(default_factory=list)
    entry_action: Optional[Action] = None
    exit_conditions: List[Condition] = field(default_factory=list)
    exit_action: Optional[Action] = None
    entered: bool = False
    exited: bool = False
    history: List[dict] = field(default_factory=list)
    parse_warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "raw_text": self.raw_text,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "complex": self.complex,
            "status": self.status,
            "entry_conditions": [c.__dict__ for c in self.entry_conditions],
            "entry_action": self.entry_action.__dict__ if self.entry_action else None,
            "exit_conditions": [c.__dict__ for c in self.exit_conditions],
            "exit_action": self.exit_action.__dict__ if self.exit_action else None,
            "entered": self.entered,
            "exited": self.exited,
            "history": list(self.history),
            "parse_warnings": list(self.parse_warnings),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Instruction":
        ec = [Condition(**c) for c in (data.get("entry_conditions") or [])]
        xc = [Condition(**c) for c in (data.get("exit_conditions") or [])]
        ea_data = data.get("entry_action")
        xa_data = data.get("exit_action")
        return cls(
            id=data.get("id", _new_id()),
            raw_text=data.get("raw_text", ""),
            created_at=data.get("created_at", time.time()),
            expires_at=data.get("expires_at", 0.0),
            complex=data.get("complex", False),
            status=data.get("status", "active"),
            entry_conditions=ec,
            entry_action=Action(**ea_data) if ea_data else None,
            exit_conditions=xc,
            exit_action=Action(**xa_data) if xa_data else None,
            entered=data.get("entered", False),
            exited=data.get("exited", False),
            history=list(data.get("history", [])),
            parse_warnings=list(data.get("parse_warnings", [])),
        )

    def add_history(self, event: str, details: str = ""):
        self.history.append(
            {"ts": time.time(), "event": event, "details": details}
        )
