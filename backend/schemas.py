"""Modelos Pydantic para las respuestas y bodies del API."""
from typing import List, Optional
from pydantic import BaseModel, Field


# ---------- Health ----------
class HealthResponse(BaseModel):
    status: str
    uptime_s: float
    bot_alive: bool
    ws_connections: int


# ---------- Posiciones ----------
class PositionOut(BaseModel):
    id: str
    entry_price: float
    amount: float
    dca_level: int
    total_invested: float
    entry_time: float
    entry_mode: str = ""
    is_frozen: bool = False
    peak_price: float = 0.0
    roi_current: float = 0.0
    current_value_usdt: float = 0.0


# ---------- Trades ----------
class TradeOut(BaseModel):
    timestamp: str  # ISO 8601
    action: str
    price: float
    amount: float
    fee: float = 0.0
    pnl: Optional[float] = None


# ---------- Decisiones ----------
class AgentDecisionOut(BaseModel):
    timestamp: str  # ISO 8601
    source: str
    action: str
    confidence: float = 0.0
    reasoning: str = ""


# ---------- Dashboard ----------
class DashboardSnapshot(BaseModel):
    mode: str  # NORMAL | INSTRUCTION
    active_instruction_id: Optional[str] = None
    price: float = 0.0
    regime: str = "LATERAL"
    regime_confidence: float = 0.0
    balance_total: float = 0.0
    usdt_disponible: float = 0.0
    btc_held: float = 0.0
    capital_inicial: float = 0.0
    portfolio_pnl: float = 0.0
    portfolio_pnl_pct: float = 0.0
    total_pnl: float = 0.0
    total_fees: float = 0.0
    total_trades: int = 0
    daily_start_balance: float = 0.0
    num_positions: int = 0
    available_slots: int = 0
    exposure_pct: float = 0.0
    rsi_14: float = 50.0
    rsi_weekly: float = 50.0
    cooldown_active: bool = False
    positions: List[PositionOut] = Field(default_factory=list)
    recent_trades: List[TradeOut] = Field(default_factory=list)
    recent_decisions: List[AgentDecisionOut] = Field(default_factory=list)
    uptime_s: float = 0.0


# ---------- Config ----------
class ProviderConfig(BaseModel):
    name: str  # gemini | claude | openai
    enabled: bool
    key_preview: str  # primeros 4 chars + "...."


class ConfigOut(BaseModel):
    prod_mode: bool
    agent_mode: str
    agent_model: str
    pausa: int
    capital_per_slot: float
    min_position_capital: float
    binance_api_key_preview: str
    binance_secret_preview: str
    providers: List[ProviderConfig]
    sell_floor: Optional[float] = None


class ConfigIn(BaseModel):
    prod_mode: Optional[bool] = None
    agent_mode: Optional[str] = None
    agent_model: Optional[str] = None
    pausa: Optional[int] = None
    capital_per_slot: Optional[float] = None
    min_position_capital: Optional[float] = None
    binance_api_key: Optional[str] = None
    binance_secret: Optional[str] = None
    google_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None


class ConfigSaveResponse(BaseModel):
    config: ConfigOut
    requires_restart: bool
    restart_reason: str = ""


# ---------- Instrucciones ----------
class ConditionOut(BaseModel):
    type: str
    value: float
    operator: str = ">="
    fired_at: float = 0.0


class ActionOut(BaseModel):
    type: str
    quantity_btc: float = 0.0
    quantity_usdt: float = 0.0
    sell_pct: float = 1.0
    target_position_id: str = ""


class InstructionOut(BaseModel):
    id: str
    raw_text: str
    created_at: float
    expires_at: float = 0.0
    complex: bool = False
    status: str
    entry_conditions: List[ConditionOut] = Field(default_factory=list)
    entry_action: Optional[ActionOut] = None
    exit_conditions: List[ConditionOut] = Field(default_factory=list)
    exit_action: Optional[ActionOut] = None
    entered: bool = False
    exited: bool = False
    history: List[dict] = Field(default_factory=list)
    parse_warnings: List[str] = Field(default_factory=list)


class InstructionPreviewIn(BaseModel):
    text: str
    complex: bool = False


class InstructionPreviewOut(BaseModel):
    parsed: InstructionOut
    can_activate: bool
    blocking_warnings: List[str] = Field(default_factory=list)


class InstructionCreateIn(BaseModel):
    text: str
    complex: bool = False
    expires_at: Optional[float] = None


# ---------- Logs ----------
class LogTail(BaseModel):
    lines: List[str]
    total: int
