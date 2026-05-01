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
  | { type: 'position_change'; data: { positions: PositionOut[] }; ts: number };

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
