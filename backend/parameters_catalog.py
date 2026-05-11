"""Catálogo de parámetros editables del bot, con metadatos para la UI.

Cada parámetro define: clave, etiqueta, tipo, rango, defaults, descripción de
para qué sirve y categoría para agrupación. El `default` debe coincidir con el
valor hardcoded en `config.py` (es lo que se aplica si parameters.json no lo
sobrescribe).

Tipos:
- "int"     → entero
- "float"   → decimal
- "percent" → decimal en código (0.15) pero la UI muestra/edita como % (15)
- "bool"    → booleano
- "select"  → string con `options`
"""
from typing import Any, List, Optional, TypedDict


class ParamDef(TypedDict, total=False):
    key: str
    label: str
    type: str
    default: Any
    min: float
    max: float
    step: float
    unit: str
    description: str
    category: str
    restart_required: bool
    options: List[str]


PARAMETER_CATALOG: List[ParamDef] = [
    # ── Trading loop ───────────────────────────────────────────────────────
    {
        "key": "PAUSA",
        "label": "Pausa entre ciclos",
        "type": "int",
        "default": 30,
        "min": 5, "max": 600, "step": 1,
        "unit": "segundos",
        "description": (
            "Tiempo de espera entre cada iteración del bot loop. Más bajo = más "
            "agresivo y más llamadas a Binance/LLM. Recomendado 15-60s."
        ),
        "category": "trading",
        "restart_required": True,
    },

    # ── Capital y posiciones ───────────────────────────────────────────────
    {
        "key": "CAPITAL_PER_SLOT",
        "label": "Capital mínimo por slot",
        "type": "float",
        "default": 650.0,
        "min": 50, "max": 10000, "step": 50,
        "unit": "USDT",
        "description": (
            "Cantidad mínima de capital necesaria antes de añadir otra posición. "
            "El número real de posiciones se calcula como balance / CAPITAL_PER_SLOT."
        ),
        "category": "capital",
        "restart_required": True,
    },
    {
        "key": "MIN_POSITION_CAPITAL",
        "label": "Capital mínimo para abrir posición",
        "type": "float",
        "default": 150.0,
        "min": 10, "max": 2000, "step": 10,
        "unit": "USDT",
        "description": (
            "Mínimo USDT requerido para abrir una nueva posición. Por debajo de "
            "este valor el agente saltará la compra (fees ~0.20% round-trip "
            "necesitan margen real)."
        ),
        "category": "capital",
        "restart_required": True,
    },
    {
        "key": "MIN_DCA_CAPITAL",
        "label": "Capital mínimo para DCA",
        "type": "float",
        "default": 50.0,
        "min": 10, "max": 1000, "step": 10,
        "unit": "USDT",
        "description": (
            "Mínimo USDT para añadir DCA a una posición existente. Más bajo "
            "que MIN_POSITION_CAPITAL porque ya hay capital invertido."
        ),
        "category": "capital",
        "restart_required": True,
    },
    {
        "key": "MAX_CAPITAL_PER_POSITION_PCT",
        "label": "Capital máx. por posición",
        "type": "percent",
        "default": 0.25,
        "min": 5, "max": 100, "step": 1,
        "description": (
            "Porcentaje máximo del balance que puede destinarse a una sola "
            "posición. Protege contra concentración en un solo trade."
        ),
        "category": "capital",
        "restart_required": True,
    },
    {
        "key": "MAX_CONCURRENT_POSITIONS",
        "label": "Máx. posiciones concurrentes (cap absoluto)",
        "type": "int",
        "default": 5,
        "min": 1, "max": 20, "step": 1,
        "description": (
            "Tope absoluto de posiciones simultáneas. El régimen activo (ALCISTA, "
            "BAJISTA, LATERAL, CRASH) puede aplicar un límite menor."
        ),
        "category": "capital",
        "restart_required": True,
    },

    # ── Gestión de riesgo ──────────────────────────────────────────────────
    {
        "key": "HARD_STOP_LOSS_PCT",
        "label": "Hard Stop Loss (red de seguridad)",
        "type": "percent",
        "default": 0.15,
        "min": 5, "max": 30, "step": 0.5,
        "description": (
            "Stop loss universal. Si una posición cae más de este porcentaje, "
            "se vende automáticamente sin negociar — incluso en Modo Instrucción. "
            "NO bajar de 5%."
        ),
        "category": "risk",
        "restart_required": True,
    },
    {
        "key": "TAKE_PROFIT_PCT",
        "label": "Take Profit base",
        "type": "percent",
        "default": 0.015,
        "min": 0.5, "max": 10, "step": 0.1,
        "description": (
            "Porcentaje de ganancia base para activar lógicas de salida. Cada "
            "régimen aplica su propio TP en REGIME_PARAMS — éste es el valor de "
            "respaldo legacy."
        ),
        "category": "risk",
        "restart_required": True,
    },
    {
        "key": "STOP_LOSS_GLOBAL_PCT",
        "label": "Stop Loss global (legacy)",
        "type": "percent",
        "default": 0.08,
        "min": 1, "max": 25, "step": 0.5,
        "description": (
            "Stop loss legacy de respaldo. Cada régimen ahora aplica su propio "
            "sl_pct en REGIME_PARAMS."
        ),
        "category": "risk",
        "restart_required": True,
    },
    {
        "key": "DAILY_LOSS_LIMIT_PCT",
        "label": "Límite de pérdida diaria",
        "type": "percent",
        "default": 0.05,
        "min": 1, "max": 15, "step": 0.5,
        "description": (
            "Si la pérdida del portafolio en el día excede este porcentaje, el "
            "bot detiene compras (puede seguir gestionando salidas)."
        ),
        "category": "risk",
        "restart_required": True,
    },
    {
        "key": "MIN_USDT_RESERVE_PCT",
        "label": "Reserva mínima USDT",
        "type": "percent",
        "default": 0.30,
        "min": 5, "max": 80, "step": 1,
        "description": (
            "Porcentaje del balance que debe permanecer en USDT en todo momento "
            "(reserva para DCA y emergencias)."
        ),
        "category": "risk",
        "restart_required": True,
    },
    {
        "key": "MAX_PORTFOLIO_EXPOSURE",
        "label": "Exposición máxima del portafolio",
        "type": "percent",
        "default": 0.70,
        "min": 20, "max": 95, "step": 1,
        "description": (
            "Porcentaje máximo del balance que puede estar invertido en BTC. "
            "Derivado de 1 - MIN_USDT_RESERVE_PCT."
        ),
        "category": "risk",
        "restart_required": True,
    },
    {
        "key": "MIN_PROFIT_AFTER_FEES_PCT",
        "label": "Ganancia mínima post-fees para SELL final",
        "type": "percent",
        "default": 0.004,
        "min": 0.1, "max": 5, "step": 0.05,
        "description": (
            "Bloquea SELL completo si el ROI no supera este umbral (cubre "
            "fees ~0.2% + margen). Stop-loss se ejecuta ignorando esta regla. "
            "PARTIAL_SELL usa el threshold más laxo MIN_PROFIT_SCALED_EXIT_PCT."
        ),
        "category": "risk",
        "restart_required": True,
    },
    {
        "key": "MIN_PROFIT_SCALED_EXIT_PCT",
        "label": "Ganancia mínima para PARTIAL_SELL (scaled exit)",
        "type": "percent",
        "default": 0.002,
        "min": 0, "max": 2, "step": 0.05,
        "description": (
            "Threshold más laxo para ventas parciales (sell_pct < 1.0). "
            "Permite hacer lock-in parcial temprano para reducir riesgo, mientras "
            "el SELL final aún requiere MIN_PROFIT_AFTER_FEES_PCT para cubrir fees."
        ),
        "category": "risk",
        "restart_required": True,
    },
    {
        "key": "RISK_PER_TRADE_PCT",
        "label": "Riesgo por operación",
        "type": "percent",
        "default": 0.02,
        "min": 0.5, "max": 10, "step": 0.1,
        "description": (
            "Porcentaje del capital arriesgado por trade (usado para sizing "
            "basado en riesgo en posiciones futuras)."
        ),
        "category": "risk",
        "restart_required": True,
    },
    {
        "key": "MIN_RISK_REWARD",
        "label": "R:R mínimo",
        "type": "float",
        "default": 2.0,
        "min": 1, "max": 10, "step": 0.1,
        "unit": "ratio",
        "description": (
            "Relación riesgo:recompensa mínima aceptable para aprobar una "
            "entrada (ganancia esperada vs distancia al SL)."
        ),
        "category": "risk",
        "restart_required": True,
    },

    # ── DCA ────────────────────────────────────────────────────────────────
    {
        "key": "DCA_BASE_UNIT_PCT",
        "label": "Unidad base DCA",
        "type": "percent",
        "default": 0.03,
        "min": 0.5, "max": 15, "step": 0.1,
        "description": (
            "Porcentaje base del capital usado por nivel de DCA. El multiplicador "
            "RSI escala este valor."
        ),
        "category": "dca",
        "restart_required": True,
    },
    {
        "key": "MAX_DCA_LEVELS",
        "label": "Niveles máximos de DCA",
        "type": "int",
        "default": 5,
        "min": 1, "max": 10, "step": 1,
        "description": (
            "Máximo de niveles DCA permitidos por posición. Más niveles = más "
            "promediado pero más capital comprometido."
        ),
        "category": "dca",
        "restart_required": True,
    },
    {
        "key": "DCA_NIVEL_1_DROP",
        "label": "Drop nivel 1 DCA (legacy)",
        "type": "percent",
        "default": 0.025,
        "min": 0.5, "max": 20, "step": 0.5,
        "description": (
            "Caída desde entrada para activar DCA nivel 1 (legacy — la lógica "
            "actual usa multiplicadores RSI por régimen)."
        ),
        "category": "dca",
        "restart_required": True,
    },
    {
        "key": "DCA_NIVEL_2_DROP",
        "label": "Drop nivel 2 DCA (legacy)",
        "type": "percent",
        "default": 0.05,
        "min": 1, "max": 30, "step": 0.5,
        "description": (
            "Caída desde entrada para DCA nivel 2 (legacy)."
        ),
        "category": "dca",
        "restart_required": True,
    },

    # ── Salidas ALCISTA (trailing + scaled exits) ───────────────────────────
    {
        "key": "TRAILING_STOP_ALCISTA_PCT",
        "label": "Trailing stop ALCISTA — caída desde peak",
        "type": "percent",
        "default": 0.007,
        "min": 0.2, "max": 3, "step": 0.05,
        "description": (
            "En régimen ALCISTA, vende la posición si el precio cae más de "
            "este % desde su pico. Más alto = filtra mejor el ruido, captura "
            "más rally; más bajo = lock-in más rápido, menor ganancia."
        ),
        "category": "exits_alcista",
        "restart_required": True,
    },
    {
        "key": "TRAILING_MIN_EXIT_ROI_ALCISTA_PCT",
        "label": "ROI mínimo para activar trailing exit ALCISTA",
        "type": "percent",
        "default": 0.007,
        "min": 0.2, "max": 3, "step": 0.05,
        "description": (
            "El trailing stop solo ejecuta si el ROI total ya alcanzó este "
            "umbral, evitando vender en pérdida por trailing prematuro."
        ),
        "category": "exits_alcista",
        "restart_required": True,
    },
    {
        "key": "SCALED_EXIT_ALCISTA_ROI_PCT",
        "label": "Scaled exit intermedio ALCISTA — ROI gatillo",
        "type": "percent",
        "default": 0.015,
        "min": 0.5, "max": 10, "step": 0.05,
        "description": (
            "Al alcanzar este ROI, vende una fracción de la posición (lock-in "
            "parcial). El resto queda para el trailing stop. Default 1.5%."
        ),
        "category": "exits_alcista",
        "restart_required": True,
    },
    {
        "key": "SCALED_EXIT_ALCISTA_SELL_PCT",
        "label": "Scaled exit intermedio ALCISTA — fracción a vender",
        "type": "percent",
        "default": 0.25,
        "min": 5, "max": 80, "step": 5,
        "description": (
            "Porcentaje de la posición a vender cuando se dispara el scaled "
            "exit intermedio. Default 25% (deja 75% para el rally completo)."
        ),
        "category": "exits_alcista",
        "restart_required": True,
    },

    # ── Filtros de entrada (Risk Guardian) ─────────────────────────────────
    {
        "key": "PEAK_GUARD_DISTANCE_PCT",
        "label": "Peak Guard — distancia mínima al swing high 48h",
        "type": "percent",
        "default": 0.015,
        "min": 0, "max": 10, "step": 0.1,
        "description": (
            "Bloquea BUY si el precio actual está dentro de este porcentaje del "
            "máximo reciente (swing_high_48h). Evita comprar cerca del techo en "
            "consolidaciones laterales. Bajar = más entradas pero mayor riesgo "
            "de comprar en pico. 0% lo desactiva."
        ),
        "category": "filters",
        "restart_required": True,
    },
    {
        "key": "ADX_BEARISH_GAP",
        "label": "ADX 1h bajista — gap mínimo -DI vs +DI",
        "type": "float",
        "default": 5.0,
        "min": 0, "max": 30, "step": 0.5,
        "description": (
            "Bloquea BUY si en 1h el -DI supera al +DI por más de este valor "
            "(ADX > 20). Confirma momentum bajista antes de pausar entradas."
        ),
        "category": "filters",
        "restart_required": True,
    },
    {
        "key": "EMA50_1H_TOLERANCE_PCT",
        "label": "Filtro macro 1H — tolerancia bajo EMA50",
        "type": "percent",
        "default": -0.05,
        "min": -20, "max": 0, "step": 0.5,
        "description": (
            "Bloquea BUY si el precio está más de este porcentaje (negativo) "
            "bajo la EMA50 de 1h. Default -5% bloquea entradas con precio muy "
            "extendido bajo la media."
        ),
        "category": "filters",
        "restart_required": True,
    },

    # ── Detección de régimen ───────────────────────────────────────────────
    {
        "key": "REGIME_ADX_TREND",
        "label": "ADX umbral tendencia",
        "type": "float",
        "default": 25,
        "min": 15, "max": 50, "step": 1,
        "description": (
            "ADX ≥ este valor indica mercado en tendencia (ALCISTA/BAJISTA según "
            "RSI semanal). Más alto = menos tendencias detectadas."
        ),
        "category": "regime",
        "restart_required": True,
    },
    {
        "key": "REGIME_ADX_LATERAL",
        "label": "ADX umbral lateral",
        "type": "float",
        "default": 20,
        "min": 10, "max": 40, "step": 1,
        "description": (
            "ADX < este valor indica mercado lateral (rangeado). Entre lateral y "
            "trend hay banda transicional."
        ),
        "category": "regime",
        "restart_required": True,
    },
    {
        "key": "REGIME_WEEKLY_RSI_BULL",
        "label": "RSI semanal alcista",
        "type": "float",
        "default": 60,
        "min": 50, "max": 80, "step": 1,
        "description": (
            "RSI semanal ≥ este valor confirma régimen ALCISTA (con ADX > "
            "REGIME_ADX_TREND)."
        ),
        "category": "regime",
        "restart_required": True,
    },
    {
        "key": "REGIME_WEEKLY_RSI_BEAR",
        "label": "RSI semanal bajista",
        "type": "float",
        "default": 40,
        "min": 20, "max": 50, "step": 1,
        "description": (
            "RSI semanal ≤ este valor confirma régimen BAJISTA."
        ),
        "category": "regime",
        "restart_required": True,
    },
    {
        "key": "CRASH_DROP_24H",
        "label": "Caída 24h para CRASH",
        "type": "percent",
        "default": -0.10,
        "min": -30, "max": -3, "step": 0.5,
        "description": (
            "Caída en 24h (negativa) que activa el protocolo CRASH. Por defecto "
            "−10%."
        ),
        "category": "regime",
        "restart_required": True,
    },
    {
        "key": "CRASH_VOLUME_RATIO",
        "label": "Volumen extremo para CRASH",
        "type": "float",
        "default": 2.0,
        "min": 1, "max": 10, "step": 0.1,
        "description": (
            "Múltiplo del volumen promedio que confirma régimen CRASH (junto con "
            "caída fuerte y FNG bajo)."
        ),
        "category": "regime",
        "restart_required": True,
    },
    {
        "key": "CRASH_FNG_MAX",
        "label": "Fear & Greed máximo CRASH",
        "type": "int",
        "default": 20,
        "min": 5, "max": 40, "step": 1,
        "description": (
            "Índice de Fear & Greed por debajo de este valor confirma pánico "
            "(componente del régimen CRASH)."
        ),
        "category": "regime",
        "restart_required": True,
    },

    # ── Agente IA ──────────────────────────────────────────────────────────
    {
        "key": "AGENT_MIN_CONFIDENCE",
        "label": "Confianza mínima del agente",
        "type": "float",
        "default": 0.5,
        "min": 0.1, "max": 0.99, "step": 0.05,
        "description": (
            "Confianza mínima requerida en una decisión del LLM para aceptarla. "
            "Por debajo se cae a las reglas."
        ),
        "category": "agent",
        "restart_required": True,
    },
    {
        "key": "AGENT_CALL_TIMEOUT",
        "label": "Timeout llamada al LLM",
        "type": "float",
        "default": 8.0,
        "min": 2, "max": 60, "step": 0.5,
        "unit": "segundos",
        "description": (
            "Tiempo máximo de espera por una respuesta del LLM. Si supera, se "
            "cae a reglas."
        ),
        "category": "agent",
        "restart_required": True,
    },
    {
        "key": "AGENT_MIN_INTERVAL",
        "label": "Intervalo mínimo entre llamadas LLM",
        "type": "int",
        "default": 60,
        "min": 10, "max": 600, "step": 5,
        "unit": "segundos",
        "description": (
            "Cooldown mínimo entre llamadas al LLM para controlar costo. El "
            "TriggerEvaluator decide cuándo llamar dentro de este rango."
        ),
        "category": "agent",
        "restart_required": True,
    },
    {
        "key": "AGENT_MAX_OUTPUT_TOKENS",
        "label": "Tokens máximos de respuesta",
        "type": "int",
        "default": 1024,
        "min": 256, "max": 4096, "step": 64,
        "description": (
            "Tope de tokens de salida del LLM. Respuesta JSON compacta normalmente "
            "necesita <512."
        ),
        "category": "agent",
        "restart_required": True,
    },

    # ── Cooldowns ──────────────────────────────────────────────────────────
    {
        "key": "COOLDOWN_AFTER_SL",
        "label": "Cooldown post-Stop Loss",
        "type": "int",
        "default": 30,
        "min": 0, "max": 200, "step": 1,
        "unit": "ciclos",
        "description": (
            "Ciclos a esperar tras un stop loss antes de permitir nueva BUY. "
            "Evita revanchismo después de un fallo."
        ),
        "category": "cooldowns",
        "restart_required": True,
    },
    {
        "key": "COOLDOWN_AFTER_WIN",
        "label": "Cooldown post-Take Profit",
        "type": "int",
        "default": 5,
        "min": 0, "max": 100, "step": 1,
        "unit": "ciclos",
        "description": (
            "Ciclos a esperar tras una venta ganadora antes de nueva BUY."
        ),
        "category": "cooldowns",
        "restart_required": True,
    },

    # ── Datos de mercado ───────────────────────────────────────────────────
    {
        "key": "CANDLES_15M",
        "label": "Velas 15m a cargar",
        "type": "int",
        "default": 100,
        "min": 50, "max": 500, "step": 10,
        "description": (
            "Número de velas de 15 minutos descargadas por ciclo (para "
            "indicadores como RSI, EMA, ADX)."
        ),
        "category": "candles",
        "restart_required": True,
    },
    {
        "key": "CANDLES_1H",
        "label": "Velas 1h a cargar",
        "type": "int",
        "default": 300,
        "min": 100, "max": 1000, "step": 50,
        "description": (
            "Número de velas de 1 hora. Mínimo 200 para EMA_200."
        ),
        "category": "candles",
        "restart_required": True,
    },
    {
        "key": "CANDLES_1W",
        "label": "Velas semanales a cargar",
        "type": "int",
        "default": 20,
        "min": 14, "max": 100, "step": 1,
        "description": (
            "Número de velas semanales para RSI semanal (clasificación de "
            "régimen)."
        ),
        "category": "candles",
        "restart_required": True,
    },
]


CATEGORIES = [
    {"id": "trading", "label": "Trading loop", "icon": "🔁"},
    {"id": "capital", "label": "Capital y posiciones", "icon": "💰"},
    {"id": "risk", "label": "Gestión de riesgo", "icon": "🛡️"},
    {"id": "dca", "label": "DCA", "icon": "📉"},
    {"id": "exits_alcista", "label": "Salidas ALCISTA", "icon": "🎢"},
    {"id": "filters", "label": "Filtros de entrada", "icon": "🎯"},
    {"id": "regime", "label": "Detección de régimen", "icon": "📊"},
    {"id": "agent", "label": "Agente IA", "icon": "🧠"},
    {"id": "cooldowns", "label": "Cooldowns", "icon": "⏳"},
    {"id": "candles", "label": "Datos de mercado", "icon": "🕯️"},
]


def get_param_def(key: str) -> Optional[ParamDef]:
    for p in PARAMETER_CATALOG:
        if p["key"] == key:
            return p
    return None


def cast_value(param_def: ParamDef, raw_value: Any) -> Any:
    """Convierte un valor recibido del UI al tipo interno correcto.
    Para 'percent', el UI envía el valor en porcentaje (15) y se almacena
    como decimal (0.15)."""
    t = param_def["type"]
    if t == "int":
        return int(raw_value)
    if t == "float":
        return float(raw_value)
    if t == "percent":
        return float(raw_value) / 100.0
    if t == "bool":
        return bool(raw_value)
    if t == "select":
        return str(raw_value)
    return raw_value


def to_display(param_def: ParamDef, internal_value: Any) -> Any:
    """Convierte el valor interno al formato esperado por el UI."""
    if param_def["type"] == "percent":
        try:
            return round(float(internal_value) * 100, 4)
        except (TypeError, ValueError):
            return 0
    return internal_value


def validate_value(param_def: ParamDef, internal_value: Any) -> Optional[str]:
    """Retorna mensaje de error si el valor está fuera de rango, o None si OK."""
    t = param_def["type"]
    if t in ("int", "float"):
        try:
            v = float(internal_value)
        except (TypeError, ValueError):
            return f"valor inválido: {internal_value}"
        # Para float/int los min/max son en unidades nativas
        mn = param_def.get("min")
        mx = param_def.get("max")
        if mn is not None and v < mn:
            return f"debe ser ≥ {mn}"
        if mx is not None and v > mx:
            return f"debe ser ≤ {mx}"
    elif t == "percent":
        # min/max están en %, pero el internal value es decimal
        try:
            v_pct = float(internal_value) * 100
        except (TypeError, ValueError):
            return f"valor inválido: {internal_value}"
        mn = param_def.get("min")
        mx = param_def.get("max")
        if mn is not None and v_pct < mn:
            return f"debe ser ≥ {mn}%"
        if mx is not None and v_pct > mx:
            return f"debe ser ≤ {mx}%"
    elif t == "select":
        opts = param_def.get("options") or []
        if internal_value not in opts:
            return f"opción inválida; debe ser una de: {opts}"
    return None
