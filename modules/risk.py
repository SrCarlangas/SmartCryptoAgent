from modules.logger import logger
from config import (
    MAX_PORTFOLIO_EXPOSURE, MAX_CAPITAL_PER_POSITION_PCT,
    MIN_USDT_RESERVE_PCT, DAILY_LOSS_LIMIT_PCT,
    MAX_DCA_LEVELS, RISK_PER_TRADE_PCT,
)


class RiskManager:
    def __init__(self, daily_loss_limit=DAILY_LOSS_LIMIT_PCT):
        self.daily_loss_limit = daily_loss_limit

    def verificar_limite_diario(self, current_balance, starting_balance_day):
        current_loss_pct = (current_balance - starting_balance_day) / starting_balance_day
        if current_loss_pct < -self.daily_loss_limit:
            logger.error(f"🛑 CRÍTICO: Límite de pérdida diaria alcanzado ({current_loss_pct*100:.2f}%).")
            return False
        return True

    def es_seguro_operar(self, current_balance, starting_balance_day):
        return self.verificar_limite_diario(current_balance, starting_balance_day)

    def validate_decision(self, decision, ctx):
        """
        Risk Guardian multi-posicion: puerta no-negociable.
        Retorna (aprobado: bool, razon_veto: str).
        """
        action = decision.action

        # Regla 1: BUY requiere slots disponibles
        if action == "BUY" and ctx.available_slots <= 0:
            return False, f"No hay slots disponibles ({ctx.num_positions} posiciones)"

        # Regla 2: DCA requiere posicion valida
        if action == "DCA":
            target = self._find_position(ctx, decision.target_position_id)
            if not target:
                return False, f"Posicion {decision.target_position_id} no encontrada para DCA"
            if target.dca_level >= MAX_DCA_LEVELS:
                return False, f"DCA nivel maximo ({MAX_DCA_LEVELS}) alcanzado para {decision.target_position_id}"

        # Regla 3: SELL requiere posicion valida
        if action == "SELL":
            target = self._find_position(ctx, decision.target_position_id)
            if not target:
                return False, f"Posicion {decision.target_position_id} no encontrada para SELL"

        # Regla 3b: PARTIAL_SELL requiere posicion valida y sell_pct valido
        if action == "PARTIAL_SELL":
            target = self._find_position(ctx, decision.target_position_id)
            if not target:
                return False, f"Posicion {decision.target_position_id} no encontrada para PARTIAL_SELL"
            if decision.sell_pct <= 0 or decision.sell_pct >= 1.0:
                return False, f"sell_pct invalido ({decision.sell_pct}) para PARTIAL_SELL"

        # Regla 4: Panico absoluto bloquea compras
        if action in ("BUY", "DCA") and ctx.sentiment_score < -0.95:
            return False, f"Panico absoluto (sentiment={ctx.sentiment_score:.2f})"

        # Regla 5: Exposicion total maxima
        if action in ("BUY", "DCA"):
            alloc = decision.suggested_allocation_pct or 0.10
            new_capital = ctx.balance_total * alloc
            new_total = ctx.total_invested + new_capital
            new_exposure = new_total / ctx.balance_total if ctx.balance_total > 0 else 1.0
            if new_exposure > MAX_PORTFOLIO_EXPOSURE:
                return False, f"Exposicion total excederia {MAX_PORTFOLIO_EXPOSURE*100:.0f}% ({new_exposure*100:.1f}%)"

        # Regla 6: Capital maximo por posicion
        if action == "BUY":
            alloc = decision.suggested_allocation_pct or 0.10
            new_capital = ctx.balance_total * alloc
            max_per_pos = ctx.balance_total * MAX_CAPITAL_PER_POSITION_PCT
            if new_capital > max_per_pos:
                return False, f"Capital por posicion excede {MAX_CAPITAL_PER_POSITION_PCT*100:.0f}%"

        # Regla 7: Filtro macro 1H para BUY
        if action == "BUY" and ctx.ema_50_1h > 0:
            if ctx.price_vs_ema50_1h < -0.05:
                return False, f"Filtro macro 1H: precio {ctx.price_vs_ema50_1h*100:.1f}% bajo EMA50_1h"

        # Regla 8: Reserva USDT minima 30%
        if action in ("BUY", "DCA"):
            alloc = decision.suggested_allocation_pct or 0.10
            new_capital = ctx.balance_total * alloc
            usdt_despues = ctx.usdt_disponible - new_capital
            reserve_pct = usdt_despues / ctx.balance_total if ctx.balance_total > 0 else 0
            if reserve_pct < MIN_USDT_RESERVE_PCT:
                return False, f"Reserva USDT caeria a {reserve_pct*100:.1f}% (min {MIN_USDT_RESERVE_PCT*100:.0f}%)"

        # Regla 9: Limite de perdida del portafolio bloquea compras
        if action in ("BUY", "DCA") and ctx.capital_inicial > 0:
            if ctx.portfolio_pnl_pct < -DAILY_LOSS_LIMIT_PCT:
                return False, (
                    f"PnL portafolio {ctx.portfolio_pnl:+.0f} ({ctx.portfolio_pnl_pct*100:+.1f}%) "
                    f"excede limite -{DAILY_LOSS_LIMIT_PCT*100:.0f}%"
                )

        return True, ""

    def calculate_position_size(self, capital, risk_pct, entry_price, stop_loss_price):
        """Sizing basado en riesgo: (capital * %risk) / |entry - SL|.
        Retorna USDT a desplegar.
        """
        risk_distance = abs(entry_price - stop_loss_price)
        if risk_distance == 0:
            return 0
        units = (capital * risk_pct) / risk_distance
        return units * entry_price

    def _find_position(self, ctx, pos_id):
        for p in ctx.positions:
            if p.id == pos_id:
                return p
        return None


class TrailingStopATR:
    def __init__(self, multiplicador=2.0):
        self.multiplicador = multiplicador
        self.high_price = 0
        self.stop_price = 0
        self.active = False

    def reset(self, entry_price, atr_inicial):
        self.high_price = entry_price
        self.stop_price = entry_price - (atr_inicial * self.multiplicador)
        self.active = True

    def update(self, current_price, current_atr):
        if not self.active:
            return False
        if current_price > self.high_price:
            self.high_price = current_price
        nuevo_stop_propuesto = self.high_price - (current_atr * self.multiplicador)
        if nuevo_stop_propuesto > self.stop_price:
            self.stop_price = nuevo_stop_propuesto
        if current_price <= self.stop_price:
            self.active = False
            return True
        return False
