from modules.agent.models import MarketContext, TradingDecision, ExecutionPlan
from modules.agent.analyst import MarketAnalyst
from modules.strategy import EstrategiaSmartDCA
from modules.risk import RiskManager
from modules.logger import logger
from config import (
    AGENT_MODE, AGENT_MIN_CONFIDENCE,
    REGIME_PARAMS, DCA_BASE_UNIT_PCT, HARD_STOP_LOSS_PCT,
    MIN_PROFIT_AFTER_FEES_PCT, MIN_PROFIT_SCALED_EXIT_PCT,
)


def _min_profit_threshold(sell_pct: float) -> float:
    """Devuelve el umbral mínimo de ROI para permitir una venta.
    PARTIAL_SELL (sell_pct < 1.0) usa un threshold más laxo porque la idea
    es lock-in parcial; el SELL final mantiene MIN_PROFIT_AFTER_FEES_PCT
    para cubrir fees de round-trip.
    """
    if sell_pct is not None and 0 < sell_pct < 1.0:
        return MIN_PROFIT_SCALED_EXIT_PCT
    return MIN_PROFIT_AFTER_FEES_PCT


class AgentOrchestrator:
    """Coordina agente IA -> risk guardian -> decision final (multi-posicion, multi-regimen)."""

    MAX_CONSECUTIVE_VETOS = 3  # tras N vetos, usar reglas sin LLM hasta que cambie el contexto

    def __init__(self, risk_manager: RiskManager, estrategia: EstrategiaSmartDCA):
        self.analyst = MarketAnalyst()
        self.risk_manager = risk_manager
        self.estrategia = estrategia
        self.mode = AGENT_MODE
        self._consecutive_vetos = 0
        self._last_veto_action = ""

    def decide(self, ctx: MarketContext, velas_15m=None, velas_1h=None) -> ExecutionPlan:
        plan = ExecutionPlan()

        # 0. Override por instrucción del usuario (modo INSTRUCTION).
        # Si hay una instrucción activa cuyas condiciones se cumplen, ejecuta
        # ese plan bypassando reglas/agente. HARD_STOP_LOSS sigue activo via
        # _check_hard_limits() en main.py (corre ANTES de orchestrator.decide).
        try:
            from modules.instructions.executor import InstructionExecutor
            inst_plan = InstructionExecutor.get_singleton().evaluate(ctx)
        except Exception as e:
            logger.warning(f"⚠️ InstructionExecutor error: {e}")
            inst_plan = None
        if inst_plan is not None:
            inst_plan.source = "instruction"
            approved, veto_reason = self.risk_manager.validate_capital_only(inst_plan, ctx)
            if not approved:
                logger.info(f"🛡️ Instruction blocked: {veto_reason}")
                inst_plan.vetoed = True
                inst_plan.veto_reason = f"Instruction blocked: {veto_reason}"
            else:
                logger.info(
                    f"📜 INSTRUCTION action={inst_plan.action} "
                    f"target={inst_plan.target_position_id or '-'} | reasoning: {inst_plan.reasoning}"
                )
            return inst_plan

        # 1. SIEMPRE pre-computar recomendacion de reglas (costo $0)
        rules_decision = self._get_rules_decision(ctx, velas_15m, velas_1h)

        # 2. Shadow: logear IA pero usar reglas
        if self.mode == "shadow":
            agent_decision = self._get_agent_decision(ctx, rules_decision)
            self._log_comparison(agent_decision, rules_decision)
            return self._decision_to_plan(rules_decision, ctx)

        # 3. Primary: LLM es el analista principal, reglas son input informativo
        if self.mode == "primary":
            # Si el agente ha sido vetado N veces seguidas, usar reglas sin gastar LLM
            if self._consecutive_vetos >= self.MAX_CONSECUTIVE_VETOS:
                logger.info(
                    f"⏭️ Saltando LLM: {self._consecutive_vetos} vetos consecutivos "
                    f"({self._last_veto_action}). Usando reglas."
                )
                # Resetear si el contexto cambio (reglas sugieren otra accion)
                if rules_decision.action != self._last_veto_action:
                    self._consecutive_vetos = 0
                else:
                    return self._decision_to_plan(rules_decision, ctx)

            agent_decision = self._get_agent_decision(ctx, rules_decision)

            if agent_decision.source in ("rules_api_failure", "rules_llm_failure"):
                logger.info(f"🔄 LLM no disponible, usando reglas directamente")
                approved, veto_reason = self.risk_manager.validate_decision(rules_decision, ctx)
                if not approved:
                    self._consecutive_vetos += 1
                    self._last_veto_action = rules_decision.action
                    logger.info(
                        f"🛡️ RISK GUARDIAN VETO ({self._consecutive_vetos}x): {veto_reason}"
                    )
                    plan.vetoed = True
                    plan.veto_reason = veto_reason
                    return plan
                self._consecutive_vetos = 0
                self._last_veto_action = ""
                return self._decision_to_plan(rules_decision, ctx)

            # Log si el agente difiere de las reglas
            if agent_decision.action != rules_decision.action:
                logger.info(
                    f"🧠 AGENTE OVERRIDE: reglas={rules_decision.action} → agente={agent_decision.action} "
                    f"(conf:{agent_decision.confidence:.2f}) | {agent_decision.reasoning}"
                )

            # ALCISTA: si reglas=BUY y agente=HOLD con baja conviccion (<0.75), confiar en las reglas.
            # El agente tiene sesgo hacia "esperar sobreventa" que no aplica en tendencia alcista.
            if (ctx.regime == "ALCISTA"
                    and rules_decision.action == "BUY"
                    and agent_decision.action == "HOLD"
                    and agent_decision.confidence < 0.75):
                logger.info(
                    f"📐 ALCISTA trust-rules: agente HOLD conf:{agent_decision.confidence:.2f} < 0.75 "
                    f"→ ejecutando BUY de reglas"
                )
                agent_decision = rules_decision

            # Si el agente confirma la accion de reglas, copiar parametros pre-calculados
            if agent_decision.action == rules_decision.action and rules_decision.action != "HOLD":
                agent_decision.target_position_id = (
                    agent_decision.target_position_id or rules_decision.target_position_id
                )
                agent_decision.suggested_allocation_pct = (
                    agent_decision.suggested_allocation_pct or rules_decision.suggested_allocation_pct
                )
                agent_decision.sell_pct = rules_decision.sell_pct
                agent_decision.exit_trigger = rules_decision.exit_trigger

            # Normalizar: PARTIAL_SELL con sell_pct>=1.0 es realmente un SELL
            if agent_decision.action == "PARTIAL_SELL" and agent_decision.sell_pct >= 1.0:
                logger.info(f"🔄 PARTIAL_SELL con sell_pct={agent_decision.sell_pct:.2f} → convertido a SELL")
                agent_decision.action = "SELL"

            # Validar que SELL/PARTIAL_SELL/DCA apuntan a posicion existente
            if agent_decision.action in ("SELL", "PARTIAL_SELL", "DCA"):
                pos_id = agent_decision.target_position_id
                if not pos_id or not self.risk_manager._find_position(ctx, pos_id):
                    logger.warning(
                        f"⚠️ {agent_decision.action} descartado: posicion '{pos_id}' no existe. "
                        f"Usando reglas."
                    )
                    return self._decision_to_plan(rules_decision, ctx)

            # Bloquear SELL/PARTIAL_SELL con ROI < MIN_PROFIT (excepto stop-loss).
            # Fase 2: PARTIAL_SELL usa threshold más laxo (MIN_PROFIT_SCALED_EXIT_PCT).
            if agent_decision.action in ("SELL", "PARTIAL_SELL"):
                pos = self.risk_manager._find_position(ctx, agent_decision.target_position_id)
                threshold = _min_profit_threshold(agent_decision.sell_pct)
                if pos and pos.roi_current < threshold:
                    regime_cfg = REGIME_PARAMS.get(ctx.regime, REGIME_PARAMS.get("LATERAL", {}))
                    sl_pct = regime_cfg.get("sl_pct", 0.08)
                    if pos.roi_current > -sl_pct and pos.roi_current > -HARD_STOP_LOSS_PCT:
                        logger.info(
                            f"⏸️ {agent_decision.action} bloqueado: ROI {pos.roi_current*100:.2f}% "
                            f"< min {threshold*100:.2f}% "
                            f"[{agent_decision.target_position_id}]"
                        )
                        return self._decision_to_plan(rules_decision, ctx)

            # Risk guardian siempre valida
            approved, veto_reason = self.risk_manager.validate_decision(agent_decision, ctx)
            if not approved:
                self._consecutive_vetos += 1
                self._last_veto_action = agent_decision.action
                logger.info(
                    f"🛡️ RISK GUARDIAN VETO ({self._consecutive_vetos}x): {veto_reason}"
                )
                plan.vetoed = True
                plan.veto_reason = veto_reason
                return plan

            # Veto roto: accion aprobada, resetear contador
            self._consecutive_vetos = 0
            self._last_veto_action = ""
            return self._decision_to_plan(agent_decision, ctx)

        # 4. Full: LLM valida, solo risk guardian limita
        if self.mode == "full":
            agent_decision = self._get_agent_decision(ctx, rules_decision)

            if agent_decision.source in ("rules_api_failure", "rules_llm_failure"):
                logger.info(f"🔄 LLM no disponible, usando reglas directamente")
                approved, veto_reason = self.risk_manager.validate_decision(rules_decision, ctx)
                if not approved:
                    logger.info(f"🛡️ RISK GUARDIAN VETO: {veto_reason}")
                    plan.vetoed = True
                    plan.veto_reason = veto_reason
                    return plan
                return self._decision_to_plan(rules_decision, ctx)

            # Bloquear SELL/PARTIAL_SELL con ROI < MIN_PROFIT (excepto stop-loss).
            # Fase 2: PARTIAL_SELL usa threshold más laxo (MIN_PROFIT_SCALED_EXIT_PCT).
            if agent_decision.action in ("SELL", "PARTIAL_SELL"):
                pos = self.risk_manager._find_position(ctx, agent_decision.target_position_id)
                threshold = _min_profit_threshold(agent_decision.sell_pct)
                if pos and pos.roi_current < threshold:
                    regime_cfg = REGIME_PARAMS.get(ctx.regime, REGIME_PARAMS.get("LATERAL", {}))
                    sl_pct = regime_cfg.get("sl_pct", 0.08)
                    if pos.roi_current > -sl_pct and pos.roi_current > -HARD_STOP_LOSS_PCT:
                        logger.info(
                            f"⏸️ {agent_decision.action} bloqueado: ROI {pos.roi_current*100:.2f}% "
                            f"< min {threshold*100:.2f}%"
                        )
                        return self._decision_to_plan(rules_decision, ctx)

            approved, veto_reason = self.risk_manager.validate_decision(agent_decision, ctx)
            if not approved:
                logger.info(f"🛡️ RISK GUARDIAN VETO: {veto_reason}")
                plan.vetoed = True
                plan.veto_reason = veto_reason
                return plan

            return self._decision_to_plan(agent_decision, ctx)

        # Fallback
        return self._decision_to_plan(rules_decision, ctx)

    def _get_agent_decision(self, ctx: MarketContext, rules_recommendation: TradingDecision = None) -> TradingDecision:
        try:
            return self.analyst.analyze(ctx, rules_recommendation=rules_recommendation)
        except Exception as e:
            logger.error(f"❌ Error critico en agente: {e}")
            decision = TradingDecision()
            decision.source = "rules_api_failure"
            return decision

    def _get_rules_decision(self, ctx: MarketContext, velas_15m, velas_1h) -> TradingDecision:
        """Logica de reglas adaptativa por regimen de mercado."""
        decision = TradingDecision(source="rules_fallback")
        regime = ctx.regime
        regime_cfg = REGIME_PARAMS.get(regime, REGIME_PARAMS["LATERAL"])
        sl_pct = regime_cfg.get("sl_pct", 0.08)

        # ── Prioridad 1: Protocolo CRASH ──
        if regime == "CRASH":
            crash_decision = self._evaluate_crash_tranches(ctx, regime_cfg)
            if crash_decision:
                return crash_decision

        # ── Prioridad 2: Stop Loss de emergencia (universal) ──
        worst_sl = None
        worst_roi = 0
        for p in ctx.positions:
            if p.roi_current <= -HARD_STOP_LOSS_PCT:
                if worst_sl is None or p.roi_current < worst_roi:
                    worst_sl = p
                    worst_roi = p.roi_current
        if worst_sl:
            decision.action = "SELL"
            decision.target_position_id = worst_sl.id
            decision.confidence = 1.0
            decision.reasoning = f"HARD SL: ROI {worst_roi*100:.1f}% [{worst_sl.id}]"
            return decision

        # ── Prioridad 3: Stop Loss por regimen ──
        for p in ctx.positions:
            if p.roi_current <= -sl_pct:
                decision.action = "SELL"
                decision.target_position_id = p.id
                decision.confidence = 1.0
                decision.reasoning = f"SL {regime} ({sl_pct*100:.0f}%): ROI {p.roi_current*100:.1f}%"
                return decision

        # ── Prioridad 4: Salidas parciales escalonadas ──
        for p in ctx.positions:
            exits = self.estrategia.evaluar_salidas_escalonadas(
                p, ctx.price, ctx.rsi_14, regime, ctx.rsi_weekly, ctx=ctx
            )
            if exits:
                trigger_name, sell_pct = exits[0]  # una a la vez
                # Fase 2: scaled exits usan threshold más laxo cuando es parcial.
                # No vender si ganancia no cubre el threshold (excepto SL ya evaluados arriba).
                threshold = _min_profit_threshold(sell_pct)
                if p.roi_current < threshold:
                    logger.info(
                        f"⏸️ Exit {trigger_name} bloqueado: ROI {p.roi_current*100:.2f}% "
                        f"< min {threshold*100:.2f}% [{p.id}]"
                    )
                    continue
                if sell_pct >= 1.0:
                    # Venta total (ej: lateral en resistencia)
                    decision.action = "SELL"
                    decision.target_position_id = p.id
                    decision.confidence = 0.85
                    decision.reasoning = f"Exit {trigger_name}: venta total [{p.id}]"
                else:
                    decision.action = "PARTIAL_SELL"
                    decision.target_position_id = p.id
                    decision.sell_pct = sell_pct
                    decision.exit_trigger = trigger_name
                    decision.confidence = 0.85
                    decision.reasoning = f"Scaled exit {trigger_name}: {sell_pct*100:.0f}% [{p.id}]"
                return decision

        # ── Prioridad 5: Take Profit / Trailing Stop ──
        tp_pct = regime_cfg.get("tp_pct")
        if tp_pct:
            if regime == "ALCISTA":
                trailing_stop_pct = regime_cfg.get("trailing_stop_pct", 0.005)
                trailing_min_roi = regime_cfg.get("trailing_min_exit_roi", 0.010)
                for p in ctx.positions:
                    if p.roi_current >= tp_pct:
                        if p.peak_price > 0:
                            trail_price = p.peak_price * (1 - trailing_stop_pct)
                            drop_pct = (p.peak_price - ctx.price) / p.peak_price
                            if ctx.price <= trail_price and p.roi_current >= trailing_min_roi:
                                decision.action = "SELL"
                                decision.target_position_id = p.id
                                decision.confidence = 0.9
                                decision.reasoning = (
                                    f"Trailing stop ALCISTA: ROI {p.roi_current*100:.2f}% "
                                    f"| pico ${p.peak_price:.0f} caida {drop_pct*100:.2f}%"
                                )
                                return decision
                        else:
                            # Sin peak aun: vender directamente al alcanzar tp_pct
                            decision.action = "SELL"
                            decision.target_position_id = p.id
                            decision.confidence = 0.85
                            decision.reasoning = (
                                f"TP ALCISTA {tp_pct*100:.1f}%: ROI {p.roi_current*100:.2f}% "
                                f"(trailing sin peak)"
                            )
                            return decision
            else:
                for p in ctx.positions:
                    if p.roi_current >= tp_pct:
                        decision.action = "SELL"
                        decision.target_position_id = p.id
                        decision.confidence = 0.9
                        decision.reasoning = (
                            f"TP {regime} ({tp_pct*100:.1f}%): ROI {p.roi_current*100:.2f}% "
                            f"| PnL portfolio: {ctx.portfolio_pnl:+.0f}"
                        )
                        return decision

        # ALCISTA: TP usa Fibonacci 1.618
        if regime == "ALCISTA" and ctx.fib_1618 > 0:
            for p in ctx.positions:
                if ctx.price >= ctx.fib_1618:
                    decision.action = "SELL"
                    decision.target_position_id = p.id
                    decision.confidence = 0.9
                    decision.reasoning = f"TP Fibonacci 1.618 ({ctx.fib_1618:.0f}): P={ctx.price:.0f}"
                    return decision

        # ── Prioridad 6: DCA con multiplicador RSI ──
        for p in ctx.positions:
            mult = self.estrategia.get_dca_multiplier(ctx.rsi_14, regime)
            if mult > 0 and p.roi_current < -0.02:  # minimo -2% drawdown para DCA
                alloc = DCA_BASE_UNIT_PCT * mult
                # Bonus bajista: precio < EMA200 → +20%
                if regime == "BAJISTA" and ctx.ema_200_1h > 0 and ctx.price < ctx.ema_200_1h:
                    bonus = regime_cfg.get("ema200_bonus", 0.20)
                    alloc *= (1 + bonus)
                decision.action = "DCA"
                decision.target_position_id = p.id
                decision.suggested_allocation_pct = min(alloc, 0.15)  # cap 15%
                decision.confidence = 0.8
                decision.reasoning = f"DCA {regime} RSI:{ctx.rsi_14:.0f} mult:{mult}x [{p.id}]"
                return decision

        # ── Prioridad 7: Nueva entrada por regimen ──
        if ctx.available_slots > 0 and velas_15m and velas_1h:
            macro_ok = self.estrategia.analizar_filtro_1h(velas_1h)
            senal, atr, modo = self.estrategia.analizar_por_regimen(velas_15m, regime, ctx)

            if senal and macro_ok:
                size_factor = regime_cfg.get("position_size_factor", 1.0)
                alloc = 0.10 * size_factor

                # Reducir tamaño de compra si portafolio está en pérdida
                if ctx.portfolio_pnl_pct < -0.03:  # pérdida > 3%
                    alloc *= 0.50  # comprar solo 50%
                    logger.info(
                        f"📊 BUY reducido 50% por PnL portafolio: {ctx.portfolio_pnl:+.0f} "
                        f"({ctx.portfolio_pnl_pct*100:+.1f}%)"
                    )

                decision.action = "BUY"
                decision.confidence = 0.75
                decision.suggested_allocation_pct = alloc
                decision.reasoning = f"{regime}/{modo} (slot {ctx.num_positions+1})"
                return decision

        return decision  # HOLD por defecto

    def _evaluate_crash_tranches(self, ctx, regime_cfg):
        """Evalua si desplegar un tranche de emergencia en protocolo CRASH."""
        tranches = regime_cfg.get("tranches", [])
        if not tranches:
            return None

        # Usar swing_high reciente como referencia de precio pre-crash
        ref_price = ctx.swing_high if ctx.swing_high > 0 else 0
        if ref_price == 0:
            return None

        drop_from_high = (ctx.price - ref_price) / ref_price

        for i, tranche in enumerate(tranches):
            if drop_from_high <= -tranche["drop_pct"]:
                # Verificar reserva minima
                min_reserve = regime_cfg.get("min_reserve_pct", 0.20)
                if ctx.usdt_reserve_pct <= min_reserve:
                    return None

                alloc = tranche["deploy_pct"] * ctx.usdt_reserve_pct
                decision = TradingDecision(source="crash_protocol")
                decision.action = "BUY"
                decision.suggested_allocation_pct = min(alloc, 0.15)
                decision.confidence = 0.7
                decision.reasoning = (
                    f"CRASH tranche {i+1}: caida {drop_from_high*100:.1f}% "
                    f"(trigger -{tranche['drop_pct']*100:.0f}%)"
                )
                return decision

        return None

    def _decision_to_plan(self, decision: TradingDecision, ctx: MarketContext) -> ExecutionPlan:
        plan = ExecutionPlan()
        plan.action = decision.action
        plan.target_position_id = decision.target_position_id
        plan.reasoning = decision.reasoning or self._default_reasoning(decision, ctx)
        plan.source = decision.source
        plan.confidence = float(getattr(decision, "confidence", 0.0) or 0.0)
        plan.sell_pct = decision.sell_pct
        plan.exit_trigger = decision.exit_trigger

        if decision.action in ("BUY", "DCA"):
            alloc_pct = decision.suggested_allocation_pct or 0.10
            plan.capital = ctx.balance_total * alloc_pct
            if ctx.price > 0:
                plan.quantity = plan.capital / ctx.price

        return plan

    def _default_reasoning(self, decision: TradingDecision, ctx: MarketContext) -> str:
        """Construye un reasoning descriptivo cuando el LLM responde sin texto.
        Útil para auditar decisiones HOLD silenciosas.
        """
        action = decision.action or "HOLD"
        regime = getattr(ctx, "regime", "?")
        rsi = getattr(ctx, "rsi_14", None)
        rsi_w = getattr(ctx, "rsi_weekly", None)
        portfolio_pnl_pct = getattr(ctx, "portfolio_pnl_pct", None)
        bits = [f"{action} en régimen {regime}"]
        if isinstance(rsi, (int, float)):
            bits.append(f"RSI:{rsi:.0f}")
        if isinstance(rsi_w, (int, float)):
            bits.append(f"RSI_w:{rsi_w:.0f}")
        if isinstance(portfolio_pnl_pct, (int, float)) and portfolio_pnl_pct:
            bits.append(f"PnL:{portfolio_pnl_pct*100:+.1f}%")
        bits.append(f"src:{decision.source}")
        return "(auto) " + " | ".join(bits)

    def _log_comparison(self, agent: TradingDecision, rules: TradingDecision):
        match = "✅ COINCIDEN" if agent.action == rules.action else "❌ DIFIEREN"
        logger.info(
            f"👁️ SHADOW {match} | "
            f"IA: {agent.action}(conf:{agent.confidence:.2f}) | "
            f"Reglas: {rules.action} | "
            f"IA reasoning: {agent.reasoning[:60]}"
        )
