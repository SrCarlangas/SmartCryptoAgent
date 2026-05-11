import time
from modules.agent.models import MarketContext
from modules.logger import logger
from config import AGENT_MIN_INTERVAL, DCA_NIVEL_1_DROP, DCA_NIVEL_2_DROP, TAKE_PROFIT_PCT


class TriggerEvaluator:
    """Evalua si se debe llamar al agente LLM. Logica local, costo $0."""

    def __init__(self):
        self.last_call_time = 0.0
        self.last_rsi = 50.0
        self.last_price = 0.0
        self.last_price_trigger_time = 0.0
        self.last_regime = "LATERAL"
        self._cooldowns: dict = {}  # key → timestamp del último disparo

    def _cd_ok(self, key: str, secs: float) -> bool:
        """True si el cooldown pasó; registra el disparo. Evita re-disparar triggers de nivel sostenido."""
        if time.time() - self._cooldowns.get(key, 0) >= secs:
            self._cooldowns[key] = time.time()
            return True
        return False

    def should_call_agent(self, ctx: MarketContext) -> bool:
        now = time.time()
        elapsed = now - self.last_call_time

        # Rate limit
        if elapsed < AGENT_MIN_INTERVAL:
            return False

        triggered = False
        reasons = []

        # Primera llamada: siempre triggear para inicializar
        if self.last_price == 0:
            reasons.append("Inicializacion")
            triggered = True
            if triggered:
                logger.info(f"🔔 TRIGGER AGENTE: {' | '.join(reasons)}")
                self._update_state(ctx)
            return triggered

        # --- Cambio de regimen ---
        if ctx.regime != self.last_regime:
            reasons.append(f"Cambio regimen: {self.last_regime}->{ctx.regime}")
            triggered = True

        # --- Triggers con posiciones abiertas (activas Y frozen) ---
        all_positions = ctx.positions  # incluye frozen desde market_data fix
        if all_positions:
            for p in all_positions:
                # ROI cruza TP (aplica a activas y frozen) — cooldown 10min para no spamear LLM
                if p.roi_current >= TAKE_PROFIT_PCT and self._cd_ok(f"tp_{p.id}", 600):
                    reasons.append(f"[{p.id}] ROI {p.roi_current*100:.1f}% cruza TP")
                    triggered = True

                # Trailing stop: precio cae desde pico con trailing activo — cooldown 5min
                if p.peak_price > 0 and p.roi_current >= 0.007:
                    drop_from_peak = (p.peak_price - ctx.price) / p.peak_price
                    if drop_from_peak >= 0.003 and self._cd_ok(f"trail_{p.id}", 300):
                        reasons.append(
                            f"[{p.id}] Trailing: -{drop_from_peak*100:.2f}% desde pico ${p.peak_price:.0f}"
                        )
                        triggered = True

                # ROI cruza 30% (scaled exit en ALCISTA)
                if p.roi_current >= 0.30 and "roi_pct_0.3" not in p.exits_taken:
                    reasons.append(f"[{p.id}] ROI {p.roi_current*100:.1f}% cruza 30% (scaled exit)")
                    triggered = True

                # DCA triggers solo en posiciones activas (no frozen) — cooldown 10min
                if not getattr(p, 'is_frozen', False):
                    if p.dca_level == 0 and p.roi_current <= -DCA_NIVEL_1_DROP and self._cd_ok(f"dca1_{p.id}", 600):
                        reasons.append(f"[{p.id}] ROI {p.roi_current*100:.1f}% cruza DCA1")
                        triggered = True
                    elif p.dca_level == 1 and p.roi_current <= -DCA_NIVEL_2_DROP and self._cd_ok(f"dca2_{p.id}", 600):
                        reasons.append(f"[{p.id}] ROI {p.roi_current*100:.1f}% cruza DCA2")
                        triggered = True

        if ctx.num_positions > 0:
            # RSI cruza 70 (partial sell trigger en ALCISTA)
            if self.last_rsi <= 70 and ctx.rsi_14 > 70:
                reasons.append(f"RSI cruzo 70 hacia arriba ({ctx.rsi_14:.1f})")
                triggered = True

            # Periodico cada 7 min si hay posiciones activas
            if elapsed >= 420:
                reasons.append("Periodico 7min (con posiciones)")
                triggered = True

        # --- Triggers sin posiciones o con slots libres ---
        if ctx.available_slots > 0:
            # RSI cruza umbrales clave
            if self.last_rsi >= 38 and ctx.rsi_14 < 38:
                reasons.append(f"RSI cruzo 38 hacia abajo ({ctx.rsi_14:.1f})")
                triggered = True
            if self.last_rsi <= 62 and ctx.rsi_14 > 62:
                reasons.append(f"RSI cruzo 62 hacia arriba ({ctx.rsi_14:.1f})")
                triggered = True
            if self.last_rsi >= 65 and ctx.rsi_14 < 65:
                reasons.append(f"RSI enfria desde rally: {self.last_rsi:.1f}->{ctx.rsi_14:.1f}")
                triggered = True

            # Precio cruza Bollinger inferior
            if self.last_price > ctx.bb_lower > 0 and ctx.price <= ctx.bb_lower:
                reasons.append("Precio cruzo BB inferior")
                triggered = True

            # Cambio de precio significativo (>0.5%) con cooldown de 2 min
            if self.last_price > 0:
                price_change = abs(ctx.price - self.last_price) / self.last_price
                if price_change > 0.005 and (now - self.last_price_trigger_time) > 120:
                    reasons.append(f"Precio cambio {price_change*100:.2f}%")
                    triggered = True
                    self.last_price_trigger_time = now

            # Periodico cada 5 min si hay slots y no hay posiciones
            if ctx.num_positions == 0 and elapsed >= 300:
                reasons.append("Periodico 5min (sin posiciones)")
                triggered = True

        # --- RSI semanal cruza 75 (scaled exit) — cooldown 15min ---
        if ctx.rsi_weekly > 75 and ctx.num_positions > 0 and self._cd_ok("rsi_w_75", 900):
            reasons.append(f"RSI semanal > 75 ({ctx.rsi_weekly:.1f})")
            triggered = True

        if triggered:
            logger.info(f"🔔 TRIGGER AGENTE: {' | '.join(reasons)}")
            self._update_state(ctx)

        return triggered

    def _update_state(self, ctx: MarketContext):
        self.last_call_time = time.time()
        self.last_rsi = ctx.rsi_14
        self.last_price = ctx.price
        self.last_regime = ctx.regime

    def force_update(self, ctx: MarketContext):
        self.last_rsi = ctx.rsi_14
        self.last_price = ctx.price
        self.last_regime = ctx.regime
