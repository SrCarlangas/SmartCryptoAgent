import { create } from 'zustand';
import type { DashboardSnapshot, InstructionOut, Mode, TickPayload } from '../api/types';

interface BotStoreState {
  dashboard: DashboardSnapshot | null;
  instructions: InstructionOut[];
  mode: Mode;
  activeInstructionId: string | null;
  wsConnected: boolean;
  lastTickTs: number;

  setDashboard: (d: DashboardSnapshot) => void;
  applyTick: (tick: TickPayload) => void;
  setInstructions: (list: InstructionOut[]) => void;
  upsertInstruction: (inst: InstructionOut) => void;
  setMode: (mode: Mode, activeId: string | null) => void;
  setWsConnected: (v: boolean) => void;
}

export const useBotStore = create<BotStoreState>((set) => ({
  dashboard: null,
  instructions: [],
  mode: 'NORMAL',
  activeInstructionId: null,
  wsConnected: false,
  lastTickTs: 0,

  setDashboard: (d) =>
    set({
      dashboard: d,
      mode: d.mode,
      activeInstructionId: d.active_instruction_id,
    }),

  applyTick: (tick) =>
    set((state) => {
      if (!state.dashboard) return { lastTickTs: Date.now() };
      const merged: DashboardSnapshot = {
        ...state.dashboard,
        price: tick.price,
        regime: tick.regime,
        regime_confidence: tick.regime_confidence,
        balance_total: tick.balance_total,
        usdt_disponible: tick.usdt_disponible,
        portfolio_pnl: tick.portfolio_pnl,
        portfolio_pnl_pct: tick.portfolio_pnl_pct,
        rsi_14: tick.rsi_14,
        rsi_weekly: tick.rsi_weekly,
        available_slots: tick.available_slots,
        num_positions: tick.num_positions,
        exposure_pct: tick.exposure_pct,
        cooldown_active: tick.cooldown_active,
      };
      return { dashboard: merged, lastTickTs: Date.now() };
    }),

  setInstructions: (list) => set({ instructions: list }),

  upsertInstruction: (inst) =>
    set((state) => {
      const idx = state.instructions.findIndex((i) => i.id === inst.id);
      const next = [...state.instructions];
      if (idx >= 0) next[idx] = inst;
      else next.unshift(inst);
      return { instructions: next };
    }),

  setMode: (mode, activeId) =>
    set((state) => ({
      mode,
      activeInstructionId: activeId,
      dashboard: state.dashboard
        ? { ...state.dashboard, mode, active_instruction_id: activeId }
        : null,
    })),

  setWsConnected: (v) => set({ wsConnected: v }),
}));
