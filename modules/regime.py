from collections import Counter
from dataclasses import dataclass
from modules.agent.models import MarketContext
from modules.logger import logger
from config import (
    REGIME_ADX_TREND, REGIME_ADX_LATERAL,
    REGIME_WEEKLY_RSI_BULL, REGIME_WEEKLY_RSI_BEAR,
    CRASH_DROP_24H, CRASH_VOLUME_RATIO, CRASH_FNG_MAX,
)


@dataclass
class RegimeResult:
    """Resultado de la deteccion de regimen."""
    regime: str              # ALCISTA, BAJISTA, LATERAL, CRASH
    confidence: float        # 0.33-1.0
    ema_signal: str
    adx_signal: str
    rsi_signal: str
    is_crash: bool
    details: str


class RegimeDetector:
    """Detecta el regimen de mercado usando 3 senales + override de crash."""

    def detect(self, ctx: MarketContext) -> RegimeResult:
        # 1. Crash check (override total)
        if self._check_crash(ctx):
            return RegimeResult(
                regime="CRASH", confidence=1.0,
                ema_signal="", adx_signal="", rsi_signal="",
                is_crash=True,
                details=f"Crash: 24h={ctx.price_change_24h*100:.1f}% Vol={ctx.volume_ratio:.1f}x FnG={ctx.fear_greed_raw}"
            )

        # 2. Tres senales independientes
        ema_sig = self._ema_signal(ctx)
        adx_sig = self._adx_signal(ctx)
        rsi_sig = self._weekly_rsi_signal(ctx)

        # 3. Voto mayoritario
        signals = [ema_sig, adx_sig, rsi_sig]
        regime, confidence = self._resolve(signals)

        details = f"EMA:{ema_sig} ADX:{adx_sig} RSI_W:{rsi_sig}"
        return RegimeResult(regime, confidence, ema_sig, adx_sig, rsi_sig, False, details)

    def _check_crash(self, ctx: MarketContext) -> bool:
        """Crash: caida >10% en 24h + volumen extremo + Fear&Greed < 20."""
        return (
            ctx.price_change_24h < CRASH_DROP_24H
            and ctx.volume_ratio > CRASH_VOLUME_RATIO
            and ctx.fear_greed_raw < CRASH_FNG_MAX
        )

    def _ema_signal(self, ctx: MarketContext) -> str:
        """Precio vs EMA_50_1h y EMA_200_1h."""
        if ctx.ema_50_1h == 0 or ctx.ema_200_1h == 0:
            return "LATERAL"
        if ctx.price > ctx.ema_50_1h and ctx.price > ctx.ema_200_1h:
            return "ALCISTA"
        if ctx.price < ctx.ema_50_1h and ctx.price < ctx.ema_200_1h:
            return "BAJISTA"
        return "LATERAL"

    def _adx_signal(self, ctx: MarketContext) -> str:
        """ADX + DI en 1h."""
        if ctx.adx_1h > REGIME_ADX_TREND:
            return "ALCISTA" if ctx.plus_di_1h > ctx.minus_di_1h else "BAJISTA"
        if ctx.adx_1h < REGIME_ADX_LATERAL:
            return "LATERAL"
        return "LATERAL"  # zona 20-25: indeterminado

    def _weekly_rsi_signal(self, ctx: MarketContext) -> str:
        """RSI semanal."""
        if ctx.rsi_weekly > REGIME_WEEKLY_RSI_BULL:
            return "ALCISTA"
        if ctx.rsi_weekly < REGIME_WEEKLY_RSI_BEAR:
            return "BAJISTA"
        return "LATERAL"

    def _resolve(self, signals: list) -> tuple:
        """Voto mayoritario. Si empate 3-way, LATERAL con confidence 0.33."""
        counts = Counter(signals)
        winner, count = counts.most_common(1)[0]
        confidence = count / len(signals)
        if count == 1:
            return "LATERAL", 0.33
        return winner, round(confidence, 2)
