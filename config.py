import os
from dotenv import load_dotenv

load_dotenv()

# --- Trading Configuration ---
SYMBOL = 'BTC/USDT'
TIMEFRAME = '15m'
TIMEFRAME_TREND = '1h'
TIMEFRAME_WEEKLY = '1w'
PAUSA = 30  # Segundos entre ciclos

# Limites de velas a obtener
CANDLES_15M = 100
CANDLES_1H = 300       # necesario para EMA_200
CANDLES_1W = 20        # para RSI semanal

# Gestion de Salida (legacy — ahora por regimen en REGIME_PARAMS)
TAKE_PROFIT_PCT = 0.015
STOP_LOSS_GLOBAL_PCT = 0.08
HARD_STOP_LOSS_PCT = 0.15   # safety net universal, nunca se negocia
DCA_NIVEL_1_DROP = 0.025
DCA_NIVEL_2_DROP = 0.05

# --- Gestion de Riesgo Universal ---
RISK_PER_TRADE_PCT = 0.02          # 1-2% del capital por operacion
MIN_RISK_REWARD = 2.0              # R:R minimo 1:2
DAILY_LOSS_LIMIT_PCT = 0.05        # 5% perdida diaria -> detener
MIN_USDT_RESERVE_PCT = 0.30        # mantener 30% en USDT siempre
MAX_PORTFOLIO_EXPOSURE = 0.70      # 70% max (derivado de 30% reserva)
DCA_BASE_UNIT_PCT = 0.03           # unidad base DCA: 2-5% del capital
MIN_PROFIT_AFTER_FEES_PCT = 0.004  # 0.4% ROI minimo para vender (cubre 0.2% fees + margen)
MAX_DCA_LEVELS = 5                 # maximo niveles DCA por posicion

# Capital
MAX_CAPITAL_PER_POSITION_PCT = 0.25  # 25% del balance por posicion
MIN_POSITION_CAPITAL = 150.0          # minimo USDT para abrir posicion (fees: $0.30 round-trip → necesita margen real)
CAPITAL_PER_SLOT = 800.0              # capital minimo por slot antes de añadir otro (escala dinamica de posiciones)

# Cooldowns
COOLDOWN_AFTER_SL = 30
COOLDOWN_AFTER_WIN = 5

# --- Deteccion de Regimen ---
REGIME_ADX_TREND = 25       # ADX > esto = tendencia
REGIME_ADX_LATERAL = 20     # ADX < esto = lateral
REGIME_WEEKLY_RSI_BULL = 60
REGIME_WEEKLY_RSI_BEAR = 40
CRASH_DROP_24H = -0.10      # caida >10% en 24h
CRASH_VOLUME_RATIO = 2.0    # volumen extremo
CRASH_FNG_MAX = 20           # Fear & Greed < 20

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
        "trailing_stop_pct": 0.005,  # Vender si cae 0.5% desde el pico
        "trailing_min_exit_roi": 0.007,  # Minimo 0.7% ROI al ejecutar trailing sell
        "min_rr": 2.5,
        "sl_pct": 0.08,
        "position_size_factor": 1.5, # posiciones ~15% del capital
        "max_positions": 10,         # cap absoluto — numero real calculado dinamicamente por capital
        "max_exposure": 0.70,        # hasta 70% desplegado
        "min_reserve": 0.30,         # 30% reserva
        "dca_table": [(40, 2.0), (50, 0.5), (65, 0.0)],
        "partial_sell_rsi75": 0.15,  # vender 15% solo cuando RSI>75
        "scaled_exits": [
            {"trigger": "roi_pct", "value": 0.30, "sell_pct": 0.25},
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
AGENT_MIN_CONFIDENCE = 0.5
AGENT_CALL_TIMEOUT = 8.0    # segundos
AGENT_MIN_INTERVAL = 60     # segundos minimo entre llamadas al LLM
AGENT_MAX_OUTPUT_TOKENS = 1024  # respuesta JSON compacta

# --- Multi-Position ---
MAX_CONCURRENT_POSITIONS = 5
