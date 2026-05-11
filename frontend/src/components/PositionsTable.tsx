import type { PositionOut } from '../api/types';
import { fmtCurrency, fmtNumber, fmtPct } from '../utils/format';

interface Props {
  positions: PositionOut[];
}

export function PositionsTable({ positions }: Props) {
  if (!positions.length) {
    return (
      <div className="text-sm text-slate-500 italic">Sin posiciones abiertas.</div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-800">
      <table className="w-full text-sm">
        <thead className="bg-slate-900/80 text-slate-400 text-xs uppercase tracking-wider">
          <tr>
            <th className="text-left px-3 py-2">ID</th>
            <th className="text-right px-3 py-2">Entrada</th>
            <th className="text-right px-3 py-2">BTC</th>
            <th className="text-right px-3 py-2">Invertido</th>
            <th className="text-right px-3 py-2">Valor actual</th>
            <th className="text-right px-3 py-2">ROI</th>
            <th className="text-right px-3 py-2">DCA</th>
            <th className="text-right px-3 py-2">Peak</th>
            <th className="text-left px-3 py-2">Estado</th>
          </tr>
        </thead>
        <tbody className="bg-slate-950/40 divide-y divide-slate-800">
          {positions.map((p) => {
            const positive = p.roi_current >= 0;
            return (
              <tr key={p.id} className="hover:bg-slate-900/40">
                <td className="px-3 py-2 font-mono text-xs">{p.id}</td>
                <td className="px-3 py-2 text-right">{fmtCurrency(p.entry_price, 0)}</td>
                <td className="px-3 py-2 text-right">{fmtNumber(p.amount, 6)}</td>
                <td className="px-3 py-2 text-right">{fmtCurrency(p.total_invested)}</td>
                <td className="px-3 py-2 text-right">{fmtCurrency(p.current_value_usdt)}</td>
                <td className={`px-3 py-2 text-right font-medium ${positive ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {fmtPct(p.roi_current)}
                </td>
                <td className="px-3 py-2 text-right">{p.dca_level}</td>
                <td className="px-3 py-2 text-right">{p.peak_price > 0 ? fmtCurrency(p.peak_price, 0) : '—'}</td>
                <td className="px-3 py-2 text-left text-xs">
                  {p.is_frozen ? <span className="text-amber-400">CONGELADA</span> : <span className="text-slate-400">activa</span>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
