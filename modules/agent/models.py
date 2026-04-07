from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class PositionSummary:
    """Resumen de una posicion individual para el agente."""
    id: str = ""
    entry_price: float = 0.0
    amount: float = 0.0
    dca_level: int = 0
    roi_current: float = 0.0
    total_invested: float = 0.0
    entry_time: float = 0.0
    entry_mode: str = ""
    exits_taken: List[str] = field(default_factory=list)
    is_frozen: bool = False  # posicion huerfana/congelada: puede venderse pero no comprarse/DCAs


@dataclass
class CrashState:
    """Estado del protocolo de crash."""
    active: bool = False
    reference_price: float = 0.0
    tranches_deployed: List[int] = field(default_factory=list)
    crash_reserve_usdt: float = 0.0
    activated_at: float = 0.0


@dataclass
class MarketContext:
    """Datos de mercado empaquetados para el agente."""
    # Precio
    price: float = 0.0
    price_change_15m: float = 0.0
    price_change_1h: float = 0.0
    price_change_24h: float = 0.0

    # Indicadores 15m
    rsi_14: float = 50.0
    rsi_prev: float = 50.0
    bb_lower: float = 0.0
    bb_mid: float = 0.0
    bb_upper: float = 0.0
    ema_21: float = 0.0
    atr_14: float = 0.0
    adx_14: float = 0.0
    plus_di: float = 0.0
    minus_di: float = 0.0
    volume_ratio: float = 1.0
    momentum: float = 0.0

    # Indicadores 1h
    ema_50_1h: float = 0.0
    price_vs_ema50_1h: float = 0.0
    ema_200_1h: float = 0.0
    price_vs_ema200_1h: float = 0.0
    adx_1h: float = 0.0
    plus_di_1h: float = 0.0
    minus_di_1h: float = 0.0

    # Semanal
    rsi_weekly: float = 50.0

    # Sentimiento
    sentiment_score: float = 0.0
    sentiment_label: str = ""
    fear_greed_raw: int = 50

    # Regimen
    regime: str = "LATERAL"
    regime_confidence: float = 0.0

    # Fibonacci
    fib_382: float = 0.0
    fib_500: float = 0.0
    fib_618: float = 0.0
    fib_1618: float = 0.0
    swing_high: float = 0.0
    swing_low: float = 0.0

    # Soporte/Resistencia
    support_price: float = 0.0
    resistance_price: float = 0.0

    # Multi-posicion
    positions: List[PositionSummary] = field(default_factory=list)
    num_positions: int = 0
    total_btc_held: float = 0.0
    total_invested: float = 0.0
    available_slots: int = 0
    exposure_pct: float = 0.0

    # Capital
    balance_total: float = 0.0
    usdt_disponible: float = 0.0
    usdt_reserve_pct: float = 0.0

    # PnL del portafolio (real, basado en balance vs capital inicial)
    capital_inicial: float = 0.0
    portfolio_pnl: float = 0.0          # balance_total - capital_inicial
    portfolio_pnl_pct: float = 0.0      # portfolio_pnl / capital_inicial

    # Contexto
    last_trade_result: str = ""
    cooldown_active: bool = False
    recent_trades_summary: str = ""
    recent_decisions_summary: str = ""


@dataclass
class TradingDecision:
    """Decision del agente analista."""
    action: str = "HOLD"  # BUY, SELL, HOLD, DCA, PARTIAL_SELL
    target_position_id: str = ""  # para SELL/DCA: cual posicion
    confidence: float = 0.0
    reasoning: str = ""
    suggested_allocation_pct: float = 0.0
    sell_pct: float = 1.0        # 1.0=venta total, 0.25=venta parcial
    exit_trigger: str = ""       # que disparo la venta parcial
    risk_assessment: str = "medium"
    market_regime: str = "unknown"
    source: str = "agent"


@dataclass
class ExecutionPlan:
    """Plan final de ejecucion despues del risk gate."""
    action: str = "HOLD"
    target_position_id: str = ""
    capital: float = 0.0
    quantity: float = 0.0
    reasoning: str = ""
    source: str = "agent"
    vetoed: bool = False
    veto_reason: str = ""
    sell_pct: float = 1.0
    exit_trigger: str = ""
