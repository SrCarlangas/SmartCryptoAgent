// Tipos TS espejo de los modelos Pydantic en backend/schemas.py

export type Mode = 'NORMAL' | 'INSTRUCTION';

export interface PositionOut {
  id: string;
  entry_price: number;
  amount: number;
  dca_level: number;
  total_invested: number;
  entry_time: number;
  entry_mode: string;
  is_frozen: boolean;
  peak_price: number;
  roi_current: number;
  current_value_usdt: number;
}

export interface TradeOut {
  timestamp: string;
  action: string;
  price: number;
  amount: number;
  fee: number;
  pnl: number | null;
}

export interface AgentDecisionOut {
  timestamp: string;
  source: string;
  action: string;
  confidence: number;
  reasoning: string;
}

export interface DashboardSnapshot {
  mode: Mode;
  active_instruction_id: string | null;
  price: number;
  regime: string;
  regime_confidence: number;
  balance_total: number;
  usdt_disponible: number;
  btc_held: number;
  capital_inicial: number;
  portfolio_pnl: number;
  portfolio_pnl_pct: number;
  total_pnl: number;
  total_fees: number;
  total_trades: number;
  daily_start_balance: number;
  num_positions: number;
  available_slots: number;
  exposure_pct: number;
  rsi_14: number;
  rsi_weekly: number;
  cooldown_active: boolean;
  positions: PositionOut[];
  recent_trades: TradeOut[];
  recent_decisions: AgentDecisionOut[];
  uptime_s: number;
}

export interface ConditionOut {
  type: string;
  value: number;
  operator: string;
  fired_at: number;
}

export interface ActionOut {
  type: string;
  quantity_btc: number;
  quantity_usdt: number;
  sell_pct: number;
  target_position_id: string;
}

export interface InstructionOut {
  id: string;
  raw_text: string;
  created_at: number;
  expires_at: number;
  complex: boolean;
  status: string;
  entry_conditions: ConditionOut[];
  entry_action: ActionOut | null;
  exit_conditions: ConditionOut[];
  exit_action: ActionOut | null;
  entered: boolean;
  exited: boolean;
  history: Array<{ ts: number; event: string; details: string }>;
  parse_warnings: string[];
}

export interface InstructionPreviewOut {
  parsed: InstructionOut;
  can_activate: boolean;
  blocking_warnings: string[];
}

export interface ProviderConfig {
  name: string;
  enabled: boolean;
  key_preview: string;
}

export interface ConfigOut {
  prod_mode: boolean;
  agent_mode: string;
  agent_model: string;
  pausa: number;
  capital_per_slot: number;
  min_position_capital: number;
  binance_api_key_preview: string;
  binance_secret_preview: string;
  providers: ProviderConfig[];
  sell_floor: number | null;
}

export interface ConfigSaveResponse {
  config: ConfigOut;
  requires_restart: boolean;
  restart_reason: string;
}

export type WSEvent =
  | { type: 'tick'; data: TickPayload; ts: number }
  | { type: 'mode_changed'; data: { mode: Mode; active_instruction_id: string | null }; ts: number }
  | { type: 'instruction_event'; data: { event: string; instruction_id: string;[k: string]: unknown }; ts: number }
  | { type: 'trade_executed'; data: TradeOut; ts: number }
  | { type: 'position_change'; data: { positions: PositionOut[] }; ts: number }
  | { type: 'restart_requested'; data: { reason: string; requested_at: number }; ts: number };

// ---------- Parámetros ----------
export interface ParameterValueOut {
  key: string;
  label: string;
  type: 'int' | 'float' | 'percent' | 'bool' | 'select';
  default: number | string | boolean;
  min: number | null;
  max: number | null;
  step: number | null;
  unit: string;
  description: string;
  category: string;
  restart_required: boolean;
  options: string[];
  current_value: number | string | boolean;
  current_display: number | string | boolean;
  is_overridden: boolean;
}

export interface ParameterCategoryOut {
  id: string;
  label: string;
  icon: string;
}

export interface ParametersResponse {
  categories: ParameterCategoryOut[];
  parameters: ParameterValueOut[];
  restart: {
    requested: boolean;
    reason: string;
    requested_at: number;
  };
}

export interface ParameterUpdateIn {
  key: string;
  value: number | string | boolean;
}

export interface ParameterUpdateOut {
  saved: string[];
  errors: Record<string, string>;
  restart_scheduled: boolean;
  restart_in_seconds_max: number;
}

// ---------- PnL diario ----------
export interface DailyPnL {
  date: string;
  realized_pnl: number;
  fees: number;
  net_pnl: number;
  trades: number;
  buys: number;
  sells: number;
  partial_sells: number;
  dcas: number;
  starting_balance: number;
  pct_of_start: number;
}

export interface DailyPnLSummary {
  total_realized_pnl: number;
  total_fees: number;
  total_trades: number;
  days_included: number;
  positive_days: number;
  negative_days: number;
  flat_days: number;
  avg_daily_pct: number;
  best_day_pnl: number;
  worst_day_pnl: number;
}

export interface DailyPnLResponse {
  days: DailyPnL[];
  summary: DailyPnLSummary;
}

export interface TickPayload {
  price: number;
  regime: string;
  regime_confidence: number;
  balance_total: number;
  usdt_disponible: number;
  portfolio_pnl: number;
  portfolio_pnl_pct: number;
  rsi_14: number;
  rsi_weekly: number;
  available_slots: number;
  num_positions: number;
  exposure_pct: number;
  cooldown_active: boolean;
}
