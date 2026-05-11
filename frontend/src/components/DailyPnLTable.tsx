import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { DailyPnL, DailyPnLResponse } from '../api/types';
import { fmtCurrency, fmtPct } from '../utils/format';

const RANGES = [
  { label: '7 días', days: 7 },
  { label: '30 días', days: 30 },
  { label: '90 días', days: 90 },
];

export function DailyPnLTable() {
  const [data, setData] = useState<DailyPnLResponse | null>(null);
  const [days, setDays] = useState(30);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function reload(d: number) {
    setLoading(true);
    setErr(null);
    try {
      const r = await api.pnlDaily(d);
      setData(r);
    } catch (e) {
      setErr(String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    reload(days);
    // refresh cada 60s
    const id = setInterval(() => reload(days), 60_000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [days]);

  // refresh on trade ws events
  useEffect(() => {
    const handler = (e: Event) => {
      const ev = (e as CustomEvent).detail as { type: string };
      if (ev?.type === 'trade_executed') {
        reload(days);
      }
    };
    window.addEventListener('bot:ws', handler);
    return () => window.removeEventListener('bot:ws', handler);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [days]);

  if (err) {
    return (
      <div className="bg-rose-900/40 border border-rose-700/50 text-rose-300 text-sm rounded-md px-3 py-2">
        Error cargando PnL diario: {err}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex gap-1">
          {RANGES.map((r) => (
            <button
              key={r.days}
              onClick={() => setDays(r.days)}
              className={`text-xs px-2 py-1 rounded ${
                r.days === days
                  ? 'bg-slate-700 text-white'
                  : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
              }`}
            >
              {r.label}
            </button>
          ))}
        </div>
        {loading && <span className="text-xs text-slate-500">cargando...</span>}
      </div>

      {data && <Summary summary={data.summary} />}
      {data && <Bars rows={data.days} />}
      {data && <Table rows={data.days} />}
    </div>
  );
}

function Summary({ summary }: { summary: DailyPnLResponse['summary'] }) {
  const positive = summary.total_realized_pnl >= 0;
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
      <Tile
        label="PnL realizado"
        value={fmtCurrency(summary.total_realized_pnl)}
        accent={positive ? 'text-emerald-400' : 'text-rose-400'}
      />
      <Tile label="Fees totales" value={fmtCurrency(summary.total_fees)} accent="text-slate-300" />
      <Tile
        label="Días positivos / negativos / planos"
        value={`${summary.positive_days} / ${summary.negative_days} / ${summary.flat_days}`}
      />
      <Tile
        label="Promedio % por día"
        value={`${summary.avg_daily_pct >= 0 ? '+' : ''}${summary.avg_daily_pct.toFixed(3)}%`}
        accent={summary.avg_daily_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}
      />
      <Tile label="Mejor día" value={fmtCurrency(summary.best_day_pnl)} accent="text-emerald-400" />
      <Tile label="Peor día" value={fmtCurrency(summary.worst_day_pnl)} accent="text-rose-400" />
      <Tile label="Total trades" value={String(summary.total_trades)} />
      <Tile label="Días incluidos" value={String(summary.days_included)} />
    </div>
  );
}

function Tile({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div className="bg-slate-900/60 border border-slate-800 rounded p-2">
      <div className="text-[10px] text-slate-500 uppercase tracking-wider">{label}</div>
      <div className={`font-semibold ${accent || 'text-slate-100'}`}>{value}</div>
    </div>
  );
}

function Bars({ rows }: { rows: DailyPnL[] }) {
  if (!rows.length) return null;
  const max = Math.max(...rows.map((r) => Math.abs(r.realized_pnl)), 1);
  return (
    <div className="bg-slate-900/40 border border-slate-800 rounded p-3">
      <div className="text-xs text-slate-400 mb-2">Distribución diaria</div>
      <div className="flex items-end gap-0.5 h-32">
        {rows.map((r) => {
          const heightPct = Math.abs(r.realized_pnl) / max * 100;
          const positive = r.realized_pnl >= 0;
          const bgColor = positive ? 'bg-emerald-500' : 'bg-rose-500';
          const isFlat = r.realized_pnl === 0;
          return (
            <div
              key={r.date}
              className="flex-1 min-w-0 flex flex-col items-stretch justify-end h-full"
              title={`${r.date}\nPnL: ${r.realized_pnl >= 0 ? '+' : ''}$${r.realized_pnl.toFixed(2)} (${r.pct_of_start >= 0 ? '+' : ''}${r.pct_of_start.toFixed(3)}%)\nTrades: ${r.trades}`}
            >
              <div
                className={`w-full ${isFlat ? 'bg-slate-700' : bgColor} ${isFlat ? 'h-0.5 mt-auto mb-0.5 opacity-50' : ''}`}
                style={isFlat ? {} : { height: `${Math.max(heightPct, 2)}%` }}
              />
            </div>
          );
        })}
      </div>
      <div className="flex items-center justify-between text-[10px] text-slate-500 mt-1">
        <span>{rows[0]?.date}</span>
        <span>{rows[rows.length - 1]?.date}</span>
      </div>
    </div>
  );
}

function Table({ rows }: { rows: DailyPnL[] }) {
  if (!rows.length) {
    return (
      <div className="text-sm text-slate-500 italic">
        Sin actividad en el rango seleccionado.
      </div>
    );
  }
  // Mostrar más reciente primero
  const ordered = [...rows].reverse();

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-800 max-h-96 overflow-y-auto">
      <table className="w-full text-sm">
        <thead className="bg-slate-900/80 text-slate-400 text-xs uppercase tracking-wider sticky top-0">
          <tr>
            <th className="text-left px-3 py-2">Fecha</th>
            <th className="text-right px-3 py-2">PnL realizado</th>
            <th className="text-right px-3 py-2">% día</th>
            <th className="text-right px-3 py-2">Fees</th>
            <th className="text-right px-3 py-2">Trades</th>
            <th className="text-right px-3 py-2">B / DCA / S / PS</th>
            <th className="text-right px-3 py-2">Saldo inicio</th>
          </tr>
        </thead>
        <tbody className="bg-slate-950/40 divide-y divide-slate-800">
          {ordered.map((r) => {
            const positive = r.realized_pnl > 0;
            const negative = r.realized_pnl < 0;
            return (
              <tr key={r.date} className="hover:bg-slate-900/40">
                <td className="px-3 py-1.5 font-mono text-xs">{r.date}</td>
                <td
                  className={`px-3 py-1.5 text-right font-medium ${
                    positive ? 'text-emerald-400' : negative ? 'text-rose-400' : 'text-slate-500'
                  }`}
                >
                  {fmtCurrency(r.realized_pnl)}
                </td>
                <td
                  className={`px-3 py-1.5 text-right ${
                    positive ? 'text-emerald-400' : negative ? 'text-rose-400' : 'text-slate-500'
                  }`}
                >
                  {fmtPct(r.pct_of_start / 100, 3)}
                </td>
                <td className="px-3 py-1.5 text-right text-slate-400">
                  {fmtCurrency(r.fees, 4)}
                </td>
                <td className="px-3 py-1.5 text-right">{r.trades}</td>
                <td className="px-3 py-1.5 text-right text-xs text-slate-400">
                  {r.buys}/{r.dcas}/{r.sells}/{r.partial_sells}
                </td>
                <td className="px-3 py-1.5 text-right text-slate-400">
                  {fmtCurrency(r.starting_balance)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
