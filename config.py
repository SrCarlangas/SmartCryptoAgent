import os
from dotenv import load_dotenv

load_dotenv()


# --- Overrides desde parameters.json (panel) ---
# Importación local para evitar dependencias circulares y poder fallar grace-
# fully si backend/ no existe en futuros deploys aislados del CLI.
def _load_param_overrides():
    try:
        from backend.parameters_store import load_parameter_overrides
        return load_parameter_overrides()
    except Exception:
        return {}


_PARAM_OVERRIDES = _load_param_overrides()


def _p(key, default, cast=None):
    """Lee parámetro: parameters.json > .env > default. Aplica cast opcional."""
    if key in _PARAM_OVERRIDES:
        v = _PARAM_OVERRIDES[key]
    else:
        v = os.getenv(key, default)
    if cast is None:
        return v
    try:
        return cast(v)
    except (TypeError, ValueError):
        return cast(default)


# --- Trading Configuration ---
SYMBOL = 'BTC/USDT'
TIMEFRAME = '15m'
TIMEFRAME_TREND = '1h'
TIMEFRAME_WEEKLY = '1w'
PAUSA = _p('PAUSA', 30, int)  # Segundos entre ciclos

# Limites de velas a obtener
CANDLES_15M = _p('CANDLES_15M', 100, int)
CANDLES_1H = _p('CANDLES_1H', 300, int)       # necesario para EMA_200
CANDLES_1W = _p('CANDLES_1W', 20, int)        # para RSI semanal

# Gestion de Salida (legacy — ahora por regimen en REGIME_PARAMS)
TAKE_PROFIT_PCT = _p('TAKE_PROFIT_PCT', 0.015, float)
STOP_LOSS_GLOBAL_PCT = _p('STOP_LOSS_GLOBAL_PCT', 0.08, float)
HARD_STOP_LOSS_PCT = _p('HARD_STOP_LOSS_PCT', 0.15, float)   # safety net universal, nunca se negocia
DCA_NIVEL_1_DROP = _p('DCA_NIVEL_1_DROP', 0.025, float)
DCA_NIVEL_2_DROP = _p('DCA_NIVEL_2_DROP', 0.05, float)

# --- Gestion de Riesgo Universal ---
RISK_PER_TRADE_PCT = _p('RISK_PER_TRADE_PCT', 0.02, float)          # 1-2% del capital por operacion
MIN_RISK_REWARD = _p('MIN_RISK_REWARD', 2.0, float)                 # R:R minimo 1:2
DAILY_LOSS_LIMIT_PCT = _p('DAILY_LOSS_LIMIT_PCT', 0.05, float)      # 5% perdida diaria -> detener
MIN_USDT_RESERVE_PCT = _p('MIN_USDT_RESERVE_PCT', 0.30, float)      # mantener 30% en USDT siempre
MAX_PORTFOLIO_EXPOSURE = _p('MAX_PORTFOLIO_EXPOSURE', 0.70, float)  # 70% max (derivado de 30% reserva)
DCA_BASE_UNIT_PCT = _p('DCA_BASE_UNIT_PCT', 0.03, float)            # unidad base DCA: 2-5% del capital
MIN_PROFIT_AFTER_FEES_PCT = _p('MIN_PROFIT_AFTER_FEES_PCT', 0.004, float)
MIN_PROFIT_SCALED_EXIT_PCT = _p('MIN_PROFIT_SCALED_EXIT_PCT', 0.002, float)  # threshold más laxo para PARTIAL_SELL
MAX_DCA_LEVELS = _p('MAX_DCA_LEVELS', 5, int)                       # maximo niveles DCA por posicion

# Capital
MAX_CAPITAL_PER_POSITION_PCT = _p('MAX_CAPITAL_PER_POSITION_PCT', 0.25, float)
MIN_POSITION_CAPITAL = _p('MIN_POSITION_CAPITAL', 150.0, float)
MIN_DCA_CAPITAL = _p('MIN_DCA_CAPITAL', 50.0, float)
CAPITAL_PER_SLOT = _p('CAPITAL_PER_SLOT', 650.0, float)

# Cooldowns
COOLDOWN_AFTER_SL = _p('COOLDOWN_AFTER_SL', 30, int)
COOLDOWN_AFTER_WIN = _p('COOLDOWN_AFTER_WIN', 5, int)

# --- Deteccion de Regimen ---
REGIME_ADX_TREND = _p('REGIME_ADX_TREND', 25, float)
REGIME_ADX_LATERAL = _p('REGIME_ADX_LATERAL', 20, float)
REGIME_WEEKLY_RSI_BULL = _p('REGIME_WEEKLY_RSI_BULL', 60, float)
REGIME_WEEKLY_RSI_BEAR = _p('REGIME_WEEKLY_RSI_BEAR', 40, float)
CRASH_DROP_24H = _p('CRASH_DROP_24H', -0.10, float)
CRASH_VOLUME_RATIO = _p('CRASH_VOLUME_RATIO', 2.0, float)
CRASH_FNG_MAX = _p('CRASH_FNG_MAX', 20, int)

# --- Filtros de entrada (Risk Guardian) ---
PEAK_GUARD_DISTANCE_PCT = _p('PEAK_GUARD_DISTANCE_PCT', 0.015, float)  # bloquea BUY si precio < N% del swing_high_48h
ADX_BEARISH_GAP = _p('ADX_BEARISH_GAP', 5.0, float)                     # bloquea BUY si -DI > +DI + N (en 1h)
EMA50_1H_TOLERANCE_PCT = _p('EMA50_1H_TOLERANCE_PCT', -0.05, float)     # bloquea BUY si precio_vs_EMA50_1h < N (negativo)

# Smart DCA RSI multipliers (tabla universal)
SMART_DCA_RSI_TABLE = [
    (25, 3.0), (35, 2.5), (45, 2.0), (55, 1.0), (65, 0.0),
]

# Parametros por regimen
REGIME_PARAMS = {
    "ALCISTA": {
        "fib_entry_low": 0.382,
        "fib_entry_high": 0.5,
        "tp_fib_extension": 1.618,
        "tp_pct": 0.010,             # Activar trailing stop desde 1.0% ROI
        "trailing_stop_pct": _p('TRAILING_STOP_ALCISTA_PCT', 0.007, float),  # Fase 2: 0.5%→0.7% (filtra ruido)
        "trailing_min_exit_roi": _p('TRAILING_MIN_EXIT_ROI_ALCISTA_PCT', 0.007, float),  # Minimo ROI al ejecutar trailing sell
        "min_rr": 2.5,
        "sl_pct": 0.08,
        "position_size_factor": 1.5, # posiciones ~15% del capital
        "max_positions": 10,         # cap absoluto — numero real calculado dinamicamente por capital
        "max_exposure": 0.70,        # hasta 70% desplegado
        "min_reserve": 0.30,         # 30% reserva
        "dca_table": [(40, 2.0), (50, 0.5), (65, 0.0)],
        "partial_sell_rsi75": 0.15,  # vender 15% solo cuando RSI>75
        # Fase 2: scaled exit intermedio +1.5%@25% (lock-in parcial sin renunciar al rally)
        # Antes era roi_pct=0.30 que nunca disparaba (dead code).
        "scaled_exits": [
            {"trigger": "roi_pct", "value": _p('SCALED_EXIT_ALCISTA_ROI_PCT', 0.015, float),
             "sell_pct": _p('SCALED_EXIT_ALCISTA_SELL_PCT', 0.25, float)},
            {"trigger": "weekly_rsi_gt", "value": 75, "sell_pct": 0.25},
            {"trigger": "resistance", "value": None, "sell_pct": 0.25},
        ],
    },
    "BAJISTA": {
        "sl_pct": 0.10,
        "tp_pct": 0.014,
        "position_size_factor": 0.75,   # posiciones mas grandes (antes 0.50)
        "max_positions": 2,              # MENOS posiciones, MAS capital para DCA
        "max_exposure": 0.60,            # max 60% → reserva 40% para DCA
        "min_reserve": 0.40,             # 40% reserva en bajista
        "usdt_reserve_target": 0.40,
        "dca_table": [(25, 3.0), (35, 2.5), (45, 2.0), (55, 1.0), (100, 0.0)],
        "ema200_bonus": 0.20,
    },
    "LATERAL": {
        "sl_pct": 0.05,
        "tp_pct": 0.015,
        "position_size_factor": 1.2,     # posiciones 12% para superar drag de fees
        "max_positions": 6,              # cap absoluto — numero real calculado dinamicamente por capital
        "max_exposure": 0.65,            # 65% max
        "min_reserve": 0.35,             # 35% reserva
        "buy_rsi_max": 40,
        "sell_rsi_min": 65,
        "support_tolerance": 0.02,
        "dca_table": [(35, 2.0), (45, 1.0), (100, 0.0)],
        "breakout_volume": 2.0,
    },
    "CRASH": {
        "sl_pct": 0.15,
        "max_positions": 1,              # una sola posicion en crash
        "max_exposure": 0.40,            # conservar 60% liquido
        "min_reserve": 0.60,
        "tranches": [
            {"drop_pct": 0.10, "deploy_pct": 0.33},
            {"drop_pct": 0.20, "deploy_pct": 0.33},
            {"drop_pct": 0.35, "deploy_pct": 0.34},
        ],
        "min_reserve_pct": 0.20,
    },
}

# --- Agent Configuration ---
AGENT_MODE = os.getenv('AGENT_MODE', 'primary')  # shadow | primary | full
AGENT_MODEL = os.getenv('AGENT_MODEL', 'gemini-2.0-flash')
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY', '')
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY', '')  # slot para integración futura
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')        # slot para integración futura
AGENT_MIN_CONFIDENCE = _p('AGENT_MIN_CONFIDENCE', 0.5, float)
AGENT_CALL_TIMEOUT = _p('AGENT_CALL_TIMEOUT', 8.0, float)
AGENT_MIN_INTERVAL = _p('AGENT_MIN_INTERVAL', 60, int)
AGENT_MAX_OUTPUT_TOKENS = _p('AGENT_MAX_OUTPUT_TOKENS', 1024, int)

# --- Multi-Position ---
MAX_CONCURRENT_POSITIONS = _p('MAX_CONCURRENT_POSITIONS', 5, int)

# --- API / Dashboard ---
API_HOST = os.getenv('API_HOST', '127.0.0.1')
API_PORT = int(os.getenv('API_PORT', '8088'))
