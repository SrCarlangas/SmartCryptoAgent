import type { DashboardSnapshot } from '../api/types';
import { fmtCurrency, fmtNumber, fmtPct } from '../utils/format';

interface Props {
  snap: DashboardSnapshot;
}

export function PnLCard({ snap }: Props) {
  const pnlPositive = snap.portfolio_pnl >= 0;
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      <Tile label="Precio BTC" value={fmtCurrency(snap.price, 0)} accent="text-amber-300" />
      <Tile
        label="PnL Portafolio"
        value={fmtCurrency(snap.portfolio_pnl)}
        sub={fmtPct(snap.portfolio_pnl_pct)}
        accent={pnlPositive ? 'text-emerald-400' : 'text-rose-400'}
      />
      <Tile label="Balance Total" value={fmtCurrency(snap.balance_total)} sub={`USDT libre: ${fmtCurrency(snap.usdt_disponible, 0)}`} />
      <Tile label="BTC Tenido" value={fmtNumber(snap.btc_held, 6)} sub={`Posiciones: ${snap.num_positions} (slots libres ${snap.available_slots})`} />
      <Tile label="Capital Inicial" value={fmtCurrency(snap.capital_inicial)} />
      <Tile label="PnL Realizado Total" value={fmtCurrency(snap.total_pnl)} sub={`Trades: ${snap.total_trades}`} />
      <Tile label="Comisiones Pagadas" value={fmtCurrency(snap.total_fees)} accent="text-slate-300" />
      <Tile
        label="RSI 15m / Semanal"
        value={`${snap.rsi_14.toFixed(1)} / ${snap.rsi_weekly.toFixed(1)}`}
        sub={`Exposición: ${(snap.exposure_pct * 100).toFixed(1)}%`}
      />
    </div>
  );
}

interface TileProps {
  label: string;
  value: string;
  sub?: string;
  accent?: string;
}

function Tile({ label, value, sub, accent }: TileProps) {
  return (
    <div className="bg-slate-900/60 border border-slate-800 rounded-lg p-3">
      <div className="text-xs text-slate-400 uppercase tracking-wider">{label}</div>
      <div className={`text-xl font-semibold mt-0.5 ${accent || 'text-slate-100'}`}>{value}</div>
      {sub && <div className="text-xs text-slate-500 mt-0.5">{sub}</div>}
    </div>
  );
}
