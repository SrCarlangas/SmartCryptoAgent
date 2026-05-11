"""GET/PUT /api/parameters — gestión de parámetros runtime del bot.

Cualquier cambio guardado dispara `BotState.request_restart()`. El bot loop
detecta el flag al inicio del próximo ciclo y reemplaza el proceso vía
`os.execv()`, lo que asegura que `main()` arranque de cero y ejecute
`reconciliar_estado()` con los nuevos valores cargados desde parameters.json.
"""
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.parameters_catalog import (
    CATEGORIES,
    PARAMETER_CATALOG,
    cast_value,
    get_param_def,
    to_display,
    validate_value,
)
from backend.parameters_store import ParametersStore
from backend.state_bridge import BotState

router = APIRouter(prefix="/api/parameters", tags=["parameters"])


class ParameterValueOut(BaseModel):
    key: str
    label: str
    type: str
    default: Any
    min: Any = None
    max: Any = None
    step: Any = None
    unit: str = ""
    description: str
    category: str
    restart_required: bool
    options: List[str] = []
    current_value: Any
    current_display: Any
    is_overridden: bool


class ParameterCategoryOut(BaseModel):
    id: str
    label: str
    icon: str = ""


class ParametersResponse(BaseModel):
    categories: List[ParameterCategoryOut]
    parameters: List[ParameterValueOut]
    restart: Dict[str, Any]


class ParameterUpdateIn(BaseModel):
    key: str
    value: Any  # raw del UI (porcentajes en %, no decimal)


class ParameterBatchUpdateIn(BaseModel):
    updates: List[ParameterUpdateIn]


class ParameterUpdateOut(BaseModel):
    saved: List[str]
    errors: Dict[str, str]
    restart_scheduled: bool
    restart_in_seconds_max: int


def _build_param_value_out(p: dict) -> ParameterValueOut:
    store = ParametersStore.get_singleton()
    overrides = store.all()
    is_over = p["key"] in overrides
    current = overrides.get(p["key"], p["default"])
    return ParameterValueOut(
        key=p["key"],
        label=p["label"],
        type=p["type"],
        default=p["default"],
        min=p.get("min"),
        max=p.get("max"),
        step=p.get("step"),
        unit=p.get("unit", ""),
        description=p["description"],
        category=p["category"],
        restart_required=p.get("restart_required", True),
        options=p.get("options", []),
        current_value=current,
        current_display=to_display(p, current),
        is_overridden=is_over,
    )


@router.get("", response_model=ParametersResponse)
def list_parameters():
    return ParametersResponse(
        categories=[ParameterCategoryOut(**c) for c in CATEGORIES],
        parameters=[_build_param_value_out(p) for p in PARAMETER_CATALOG],
        restart=BotState.get().get_restart_info() if BotState.is_initialized() else {
            "requested": False, "reason": "", "requested_at": 0.0,
        },
    )


@router.put("", response_model=ParameterUpdateOut)
def update_parameters(body: ParameterBatchUpdateIn):
    if not body.updates:
        raise HTTPException(400, "No hay cambios en la solicitud.")

    store = ParametersStore.get_singleton()
    saved: List[str] = []
    errors: Dict[str, str] = {}
    needs_restart = False
    new_values: Dict[str, Any] = {}

    for upd in body.updates:
        pdef = get_param_def(upd.key)
        if not pdef:
            errors[upd.key] = "parámetro desconocido"
            continue
        try:
            internal = cast_value(pdef, upd.value)
        except Exception as e:
            errors[upd.key] = f"casting falló: {e}"
            continue
        err = validate_value(pdef, internal)
        if err:
            errors[upd.key] = err
            continue
        new_values[upd.key] = internal
        saved.append(upd.key)
        if pdef.get("restart_required", True):
            needs_restart = True

    if new_values:
        store.set_many(new_values)

    if needs_restart and BotState.is_initialized():
        keys_str = ", ".join(saved[:5]) + ("..." if len(saved) > 5 else "")
        BotState.get().request_restart(f"Parámetros actualizados: {keys_str}")

    # El bot revisa el flag al inicio de cada ciclo; el peor caso de espera es
    # PAUSA segundos. Exponemos PAUSA al cliente como hint.
    try:
        from config import PAUSA
        max_wait = int(PAUSA) + 5
    except Exception:
        max_wait = 35

    return ParameterUpdateOut(
        saved=saved,
        errors=errors,
        restart_scheduled=needs_restart,
        restart_in_seconds_max=max_wait,
    )


@router.post("/{key}/reset", response_model=ParameterValueOut)
def reset_parameter(key: str):
    pdef = get_param_def(key)
    if not pdef:
        raise HTTPException(404, "parámetro desconocido")
    store = ParametersStore.get_singleton()
    store.reset(key)
    if pdef.get("restart_required", True) and BotState.is_initialized():
        BotState.get().request_restart(f"Parámetro {key} restaurado al default")
    return _build_param_value_out(pdef)
