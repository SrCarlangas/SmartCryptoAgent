import type { TradeOut } from '../api/types';
import { fmtCurrency, fmtNumber } from '../utils/format';

interface Props {
  trades: TradeOut[];
}

const ACTION_COLORS: Record<string, string> = {
  BUY: 'text-emerald-400',
  DCA: 'text-cyan-400',
  SELL: 'text-rose-400',
  PARTIAL_SELL: 'text-amber-400',
};

export function TradesTable({ trades }: Props) {
  if (!trades.length) {
    return <div className="text-sm text-slate-500 italic">Sin trades aún.</div>;
  }

  // Mostrar más reciente primero
  const ordered = [...trades].reverse();

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-800 max-h-96 overflow-y-auto">
      <table className="w-full text-sm">
        <thead className="bg-slate-900/80 text-slate-400 text-xs uppercase tracking-wider sticky top-0">
          <tr>
            <th className="text-left px-3 py-2">Cuándo</th>
            <th className="text-left px-3 py-2">Acción</th>
            <th className="text-right px-3 py-2">Precio</th>
            <th className="text-right px-3 py-2">BTC</th>
            <th className="text-right px-3 py-2">Costo / Producto</th>
            <th className="text-right px-3 py-2">Comisión</th>
            <th className="text-right px-3 py-2">PnL</th>
          </tr>
        </thead>
        <tbody className="bg-slate-950/40 divide-y divide-slate-800">
          {ordered.map((t, idx) => {
            const value = t.price * t.amount;
            const isoDate = (t.timestamp || '').slice(0, 19).replace('T', ' ');
            const cls = ACTION_COLORS[t.action] || 'text-slate-300';
            return (
              <tr key={`${t.timestamp}-${idx}`} className="hover:bg-slate-900/40">
                <td className="px-3 py-2 text-slate-400 text-xs">{isoDate}</td>
                <td className={`px-3 py-2 font-semibold ${cls}`}>{t.action}</td>
                <td className="px-3 py-2 text-right">{fmtCurrency(t.price, 0)}</td>
                <td className="px-3 py-2 text-right">{fmtNumber(t.amount, 6)}</td>
                <td className="px-3 py-2 text-right">{fmtCurrency(value)}</td>
                <td className="px-3 py-2 text-right text-slate-400">{fmtCurrency(t.fee, 4)}</td>
                <td className={`px-3 py-2 text-right ${t.pnl == null ? 'text-slate-500' : t.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {t.pnl == null ? '—' : fmtCurrency(t.pnl)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
