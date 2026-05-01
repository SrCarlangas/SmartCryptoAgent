"""Endpoints de gestión de instrucciones.

La lógica real (parser/executor/store) vive en `modules/instructions/`.
Este router es solo el puente HTTP.
"""
from typing import List

from fastapi import APIRouter, HTTPException

from backend.schemas import (
    ActionOut,
    ConditionOut,
    InstructionCreateIn,
    InstructionOut,
    InstructionPreviewIn,
    InstructionPreviewOut,
)

router = APIRouter(prefix="/api/instructions", tags=["instructions"])


def _to_out(inst) -> InstructionOut:
    return InstructionOut(
        id=inst.id,
        raw_text=inst.raw_text,
        created_at=inst.created_at,
        expires_at=inst.expires_at,
        complex=inst.complex,
        status=inst.status,
        entry_conditions=[
            ConditionOut(
                type=c.type,
                value=c.value,
                operator=c.operator,
                fired_at=c.fired_at,
            )
            for c in (inst.entry_conditions or [])
        ],
        entry_action=ActionOut(
            type=inst.entry_action.type,
            quantity_btc=inst.entry_action.quantity_btc,
            quantity_usdt=inst.entry_action.quantity_usdt,
            sell_pct=inst.entry_action.sell_pct,
            target_position_id=inst.entry_action.target_position_id,
        )
        if inst.entry_action
        else None,
        exit_conditions=[
            ConditionOut(
                type=c.type,
                value=c.value,
                operator=c.operator,
                fired_at=c.fired_at,
            )
            for c in (inst.exit_conditions or [])
        ],
        exit_action=ActionOut(
            type=inst.exit_action.type,
            quantity_btc=inst.exit_action.quantity_btc,
            quantity_usdt=inst.exit_action.quantity_usdt,
            sell_pct=inst.exit_action.sell_pct,
            target_position_id=inst.exit_action.target_position_id,
        )
        if inst.exit_action
        else None,
        entered=inst.entered,
        exited=inst.exited,
        history=list(inst.history or []),
        parse_warnings=list(inst.parse_warnings or []),
    )


@router.get("", response_model=List[InstructionOut])
def list_instructions():
    from modules.instructions.store import InstructionStore

    store = InstructionStore.get_singleton()
    return [_to_out(i) for i in store.all()]


@router.post("/preview", response_model=InstructionPreviewOut)
def preview(body: InstructionPreviewIn):
    from modules.instructions.parser import parse_instruction
    from modules.instructions.executor import InstructionExecutor

    parsed = parse_instruction(body.text, complex_mode=body.complex)
    blocking = InstructionExecutor.get_singleton().validate_against_state(parsed)
    return InstructionPreviewOut(
        parsed=_to_out(parsed),
        can_activate=len(blocking) == 0,
        blocking_warnings=blocking,
    )


@router.post("", response_model=InstructionOut)
def create(body: InstructionCreateIn):
    from modules.instructions.parser import parse_instruction
    from modules.instructions.store import InstructionStore
    from modules.instructions.executor import InstructionExecutor
    from backend.state_bridge import BotState

    store = InstructionStore.get_singleton()
    if store.has_active():
        raise HTTPException(
            409,
            "Ya hay una instrucción activa. Cancélala primero o espera a que termine.",
        )

    parsed = parse_instruction(body.text, complex_mode=body.complex)
    if body.expires_at:
        parsed.expires_at = body.expires_at

    blocking = InstructionExecutor.get_singleton().validate_against_state(parsed)
    if blocking:
        raise HTTPException(400, "; ".join(blocking))

    store.add(parsed)

    bs = BotState.get()
    bs.set_mode("INSTRUCTION", parsed.id)
    bs.broadcast_instruction_event(
        "created",
        {"instruction_id": parsed.id, "raw_text": parsed.raw_text},
    )
    return _to_out(parsed)


@router.post("/{instruction_id}/cancel", response_model=InstructionOut)
def cancel(instruction_id: str):
    from modules.instructions.store import InstructionStore
    from backend.state_bridge import BotState

    store = InstructionStore.get_singleton()
    inst = store.get(instruction_id)
    if not inst:
        raise HTTPException(404, "Instrucción no encontrada")
    if inst.status not in ("active", "triggered"):
        raise HTTPException(400, f"No se puede cancelar (status={inst.status})")

    store.set_status(instruction_id, "cancelled", reason="manual")

    bs = BotState.get()
    bs.set_mode("NORMAL", None)
    bs.broadcast_instruction_event(
        "cancelled", {"instruction_id": instruction_id, "reason": "manual"}
    )
    return _to_out(store.get(instruction_id))
