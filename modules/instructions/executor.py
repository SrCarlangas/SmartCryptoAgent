"""Executor de instrucciones: evalúa condiciones cada ciclo y genera ExecutionPlan.

Se enchufa al inicio de `AgentOrchestrator.decide()`. Si retorna un plan no-None,
ese plan se ejecuta y se bypassea reglas/agente. El HARD_STOP_LOSS sigue activo
(se evalúa antes en `_check_hard_limits` de main.py).
"""
import threading
from typing import List, Optional

from modules.agent.models import ExecutionPlan
from modules.instructions.models import Action, Condition, Instruction
from modules.instructions.store import InstructionStore


class InstructionExecutor:
    _instance: Optional["InstructionExecutor"] = None
    _init_lock = threading.RLock()

    def __init__(self):
        self.store = InstructionStore.get_singleton()
        # Callbacks set externamente para evitar import circular
        self._on_event = None  # callable(event_type: str, payload: dict)

    @classmethod
    def get_singleton(cls) -> "InstructionExecutor":
        with cls._init_lock:
            if cls._instance is None:
                cls._instance = InstructionExecutor()
            return cls._instance

    def set_event_callback(self, fn):
        self._on_event = fn

    def _emit(self, event_type: str, payload: dict):
        if self._on_event:
            try:
                self._on_event(event_type, payload)
            except Exception:
                pass

    def evaluate(self, ctx) -> Optional[ExecutionPlan]:
        """Llamado al inicio de `decide()`. Retorna plan si hay instrucción que ejecutar."""
        # Limpieza de TTL
        expired = self.store.expire_check()
        for eid in expired:
            self._emit("expired", {"instruction_id": eid})

        inst = self.store.get_active()
        if not inst:
            return None

        if inst.complex:
            # M4: aquí va la llamada LLM. Por ahora, no se ejecutan instrucciones complejas.
            return None

        if not inst.entered:
            # Evaluar entrada
            if self._all_conditions_met(inst.entry_conditions, ctx):
                plan = self._build_plan_from_action(inst.entry_action, ctx)
                if plan:
                    self.store.mark_entered(
                        inst.id, f"entry @ price={ctx.price:.2f}, rsi={ctx.rsi_14:.1f}"
                    )
                    self._emit(
                        "triggered",
                        {
                            "instruction_id": inst.id,
                            "phase": "entry",
                            "price": ctx.price,
                        },
                    )
                    # Si no hay exit_conditions, la instrucción se completa al ejecutar entry
                    if not inst.exit_conditions:
                        self.store.set_status(inst.id, "completed", "no exit conditions")
                        self._emit("completed", {"instruction_id": inst.id})
                    return plan
            return None

        # entered=True, evaluar salida
        if self._all_conditions_met(inst.exit_conditions, ctx):
            plan = self._build_plan_from_action(inst.exit_action, ctx)
            if plan:
                self.store.mark_exited(
                    inst.id, f"exit @ price={ctx.price:.2f}"
                )
                self._emit("completed", {"instruction_id": inst.id})
                return plan
        return None

    def _all_conditions_met(self, conditions: List[Condition], ctx) -> bool:
        if not conditions:
            return False
        for cond in conditions:
            if not self._condition_met(cond, ctx):
                return False
        return True

    def _condition_met(self, cond: Condition, ctx) -> bool:
        ctx_value = self._extract_ctx_value(cond.type, ctx)
        if ctx_value is None:
            return False
        op = cond.operator
        if op == ">=":
            return ctx_value >= cond.value
        if op == "<=":
            return ctx_value <= cond.value
        if op == ">":
            return ctx_value > cond.value
        if op == "<":
            return ctx_value < cond.value
        if op == "==":
            return abs(ctx_value - cond.value) < 1e-6
        return False

    def _extract_ctx_value(self, cond_type: str, ctx) -> Optional[float]:
        if cond_type in ("price_above", "price_below"):
            return float(getattr(ctx, "price", 0) or 0)
        if cond_type in ("rsi_above", "rsi_below"):
            return float(getattr(ctx, "rsi_14", 50) or 50)
        if cond_type in ("roi_above", "roi_below"):
            # ROI del portafolio
            return float(getattr(ctx, "portfolio_pnl_pct", 0) or 0)
        if cond_type == "time_after":
            import time as _t
            return _t.time()
        return None

    def _build_plan_from_action(self, action: Optional[Action], ctx) -> Optional[ExecutionPlan]:
        if not action:
            return None
        plan = ExecutionPlan()
        plan.action = action.type
        plan.source = "instruction"
        plan.confidence = 1.0  # instrucción explícita del usuario → confianza máxima
        plan.reasoning = f"User instruction: {action.type}"
        plan.sell_pct = action.sell_pct
        plan.target_position_id = action.target_position_id

        price = float(getattr(ctx, "price", 0) or 0)
        if price <= 0:
            return None

        if action.type in ("BUY",):
            if action.quantity_btc > 0:
                plan.quantity = action.quantity_btc
                plan.capital = action.quantity_btc * price
            elif action.quantity_usdt > 0:
                plan.capital = action.quantity_usdt
                plan.quantity = action.quantity_usdt / price
            else:
                return None

        elif action.type in ("SELL", "PARTIAL_SELL"):
            if action.target_position_id == "any" or not action.target_position_id:
                # Tomar la primera posición disponible
                positions = getattr(ctx, "positions", []) or []
                if not positions:
                    return None
                plan.target_position_id = positions[0].id
            # cantidad se calcula desde la posición en main.py al ejecutar la venta

        return plan

    # ──────────────────────── BLOQUEO DE FLUJO NORMAL ──────────────────────
    # Cuando hay una instrucción activa esperando que se cumpla su trigger,
    # el bot NO debe ejecutar acciones del mismo "lado" (compra/venta) del
    # flujo normal. Esto refleja la intención del usuario: si dijo "vende
    # cuando supere $X", está esperando ESE momento; no quiere que el bot
    # venda antes con TP/trailing/scaled exit.
    #
    # Excepciones intencionales:
    # - HARD_STOP_LOSS (corre en main._check_hard_limits ANTES del orchestrator).
    # - SL por régimen: se mantiene activo por safety; si la posición cae
    #   abruptamente, mejor cerrar que mantenerla por la instrucción.

    def should_block_action(self, action: str, source: str = "") -> tuple:
        """Retorna (blocked: bool, reason: str) según si hay una instrucción
        activa esperando una acción del mismo grupo que `action`.

        Reglas:
        - Si entry_action.type ∈ {SELL, PARTIAL_SELL} y entered=False
          → bloquea SELL y PARTIAL_SELL del flujo normal.
        - Si entry_action.type ∈ {BUY, DCA} y entered=False
          → bloquea BUY y DCA del flujo normal.
        - HARD_STOP_LOSS (source='hard_limit') nunca se bloquea.
        - SL por régimen (source contains 'SL'): por defecto NO se bloquea
          (decisión conservadora para evitar pérdidas mayores).
        """
        # Excepciones que NO se bloquean
        if source == "hard_limit":
            return False, ""

        inst = self.store.get_active()
        if not inst or inst.entered or not inst.entry_action:
            return False, ""

        sell_actions = {"SELL", "PARTIAL_SELL"}
        buy_actions = {"BUY", "DCA"}
        pending_type = inst.entry_action.type
        pending_group = sell_actions if pending_type in sell_actions else (
            buy_actions if pending_type in buy_actions else set()
        )

        if action in pending_group:
            return True, (
                f"esperando trigger de instrucción «{inst.raw_text[:60]}»"
            )
        return False, ""

    def has_blocking_instruction(self) -> dict:
        """Info ligera para el frontend: ¿hay instrucción activa bloqueando?

        Retorna dict con: {active: bool, action_type: str, raw_text: str}
        o {active: False} si no hay nada esperando.
        """
        inst = self.store.get_active()
        if not inst or inst.entered or not inst.entry_action:
            return {"active": False}
        sell_actions = {"SELL", "PARTIAL_SELL"}
        pending_type = inst.entry_action.type
        group = "SELL" if pending_type in sell_actions else "BUY"
        return {
            "active": True,
            "blocks_group": group,
            "instruction_id": inst.id,
            "raw_text": inst.raw_text,
            "pending_action": pending_type,
        }

    def validate_against_state(self, inst: Instruction) -> List[str]:
        """Pre-flight check: detecta cantidades imposibles, posiciones inexistentes, etc."""
        warnings = []

        # Si está marcada como compleja sin LLM disponible
        if inst.complex:
            warnings.append("Modo complejo aún no soportado (requiere integración LLM en M4).")

        if not inst.entry_action and not inst.exit_action:
            warnings.append("Instrucción sin acciones ejecutables.")

        for action in (inst.entry_action, inst.exit_action):
            if not action:
                continue
            if action.type == "BUY":
                if action.quantity_btc <= 0 and action.quantity_usdt <= 0:
                    warnings.append("Acción BUY sin cantidad (BTC o USDT).")

        # Validación contra balance: requiere ctx — se hace al ejecutar
        return warnings
