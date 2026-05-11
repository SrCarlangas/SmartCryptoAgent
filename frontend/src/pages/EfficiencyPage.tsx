import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type {
  DistributionResponse,
  EfficiencySummary as EffSummary,
  TradePostmortemResponse,
  VetoPostmortemResponse,
} from '../api/types';
import { fmtCurrency } from '../utils/format';

const RANGES = [
  { label: '3 días', days: 3 },
  { label: '7 días', days: 7 },
  { label: '14 días', days: 14 },
  { label: '30 días', days: 30 },
];

export function EfficiencyPage() {
  const [days, setDays] = useState(7);
  const [lookahead, setLookahead] = useState(4);
  const [summary, setSummary] = useState<EffSummary | null>(null);
  const [postmortem, setPostmortem] = useState<TradePostmortemResponse | null>(null);
  const [distribution, setDistribution] = useState<DistributionResponse | null>(null);
  const [vetos, setVetos] = useState<VetoPostmortemResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function reload() {
    setLoading(true);
    setErr(null);
    try {
      const [s, pm, d, vp] = await Promise.all([
        api.efficiencySummary(days),
        api.efficiencyTradePostmortem(days, lookahead),
        api.efficiencyDistribution(Math.max(days, 14)),
        api.efficiencyVetoPostmortem(Math.max(days, 14)),
      ]);
      setSummary(s);
      setPostmortem(pm);
      setDistribution(d);
      setVetos(vp);
    } catch (e) {
      setErr(String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    reload();
    const id = setInterval(reload, 60_000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [days, lookahead]);

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">Análisis de eficiencia</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Mide cuánto se está dejando en la mesa. Sin modificar el comportamiento del bot.
          </p>
        </div>
        <div className="flex gap-3 items-center">
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
          <div className="flex items-center gap-1.5 text-xs text-slate-500">
            <span>Lookahead:</span>
            <select
              value={lookahead}
              onChange={(e) => setLookahead(Number(e.target.value))}
              className="bg-slate-800 border border-slate-700 rounded px-1.5 py-0.5 text-slate-200"
            >
              <option value={1}>1h</option>
              <option value={2}>2h</option>
              <option value={4}>4h</option>
              <option value={8}>8h</option>
              <option value={24}>24h</option>
            </select>
          </div>
          {loading && <span className="text-xs text-slate-500">cargando...</span>}
        </div>
      </div>

      {err && (
        <div className="bg-rose-900/40 border border-rose-700/50 text-rose-300 text-sm rounded-md px-3 py-2">
          {err}
        </div>
      )}

      {summary && <SummaryCard summary={summary} />}
      {distribution && <DistributionCard data={distribution} />}
      {postmortem && <PostmortemTable data={postmortem} />}
      {vetos && <VetoTable data={vetos} />}
    </div>
  );
}

// ─────────── Componentes ───────────

function SummaryCard({ summary }: { summary: EffSummary }) {
  const recommendations = (summary.recommendation || '').split(' · ').filter(Boolean);
  const isHealthy = recommendations.length === 1 && recommendations[0].includes('razonables');

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <Tile
          label="PnL realizado"
          value={fmtCurrency(summary.total_pnl)}
          accent={summary.total_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}
        />
        <Tile
          label="Fee burden"
          value={`${summary.fee_burden_pct.toFixed(1)}%`}
          accent={
            summary.fee_burden_pct > 18
              ? 'text-rose-400'
              : summary.fee_burden_pct > 12
              ? 'text-amber-400'
              : 'text-emerald-400'
          }
          sub="objetivo <12%"
        />
        <Tile
          label="PnL prom. por SELL"
          value={fmtCurrency(summary.avg_pnl_per_sell)}
          sub={`mediana ${fmtCurrency(summary.median_pnl_per_sell)}`}
        />
        <Tile
          label="Total SELLs"
          value={String(summary.total_sells)}
          sub={`fees: ${fmtCurrency(summary.total_fees)}`}
        />
        <Tile
          label="Micro-wins (<$1)"
          value={`${summary.pct_micro_wins.toFixed(1)}%`}
          accent={summary.pct_micro_wins > 12 ? 'text-amber-400' : 'text-slate-300'}
          sub="objetivo <8%"
        />
        <Tile
          label="Ventas en pérdida"
          value={`${summary.pct_negative_sells.toFixed(1)}%`}
          accent={summary.pct_negative_sells > 5 ? 'text-rose-400' : 'text-slate-300'}
          sub="objetivo <5%"
        />
        <Tile
          label="Missed gain promedio"
          value={`${summary.avg_missed_pct >= 0 ? '+' : ''}${summary.avg_missed_pct.toFixed(2)}%`}
          accent={
            summary.avg_missed_pct > 0.5
              ? 'text-amber-400'
              : summary.avg_missed_pct > 0.3
              ? 'text-slate-200'
              : 'text-emerald-400'
          }
          sub={`${summary.sells_with_significant_miss} ventas con miss >1%`}
        />
        <Tile
          label="Vetos rentables"
          value={`${summary.profitable_vetos_pct.toFixed(0)}%`}
          accent={summary.profitable_vetos_pct > 40 ? 'text-amber-400' : 'text-slate-300'}
          sub={`${summary.veto_count} vetos`}
        />
      </div>

      <div
        className={`rounded-lg p-3 border ${
          isHealthy
            ? 'bg-emerald-950/30 border-emerald-700/40'
            : 'bg-amber-950/30 border-amber-700/40'
        }`}
      >
        <div className="text-xs uppercase tracking-wider text-slate-400 mb-1">
          Diagnóstico automatizado
        </div>
        {isHealthy ? (
          <div className="text-sm text-emerald-300">
            ✓ {recommendations[0]}
          </div>
        ) : (
          <ul className="text-sm text-amber-200 space-y-1">
            {recommendations.map((r, i) => (
              <li key={i}>• {r}</li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function Tile({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: string;
}) {
  return (
    <div className="bg-slate-900/60 border border-slate-800 rounded-lg p-2.5">
      <div className="text-[10px] text-slate-500 uppercase tracking-wider">{label}</div>
      <div className={`text-lg font-semibold mt-0.5 ${accent || 'text-slate-100'}`}>{value}</div>
      {sub && <div className="text-[10px] text-slate-500 mt-0.5">{sub}</div>}
    </div>
  );
}

function DistributionCard({ data }: { data: DistributionResponse }) {
  const maxCount = Math.max(...data.buckets.map((b) => b.count), 1);
  return (
    <div>
      <h2 className="text-sm uppercase tracking-wider text-slate-400 mb-2">
        Distribución de PnL por venta
      </h2>
      <div className="bg-slate-900/40 border border-slate-800 rounded-lg p-3">
        <div className="grid grid-cols-1 md:grid-cols-[1fr_240px] gap-4 items-center">
          <div className="space-y-1">
            {data.buckets.map((b) => {
              const pct = (b.count / maxCount) * 100;
              const isLoss = b.range_low < 0;
              const isMicro = b.range_high <= 1.0 && !isLoss;
              return (
                <div key={b.label} className="flex items-center gap-2 text-xs">
                  <div className="w-20 text-slate-400 text-right shrink-0">{b.label}</div>
                  <div className="flex-1 h-5 bg-slate-950 rounded relative overflow-hidden">
                    <div
                      className={`h-full ${
                        isLoss
                          ? 'bg-rose-500'
                          : isMicro
                          ? 'bg-amber-500'
                          : 'bg-emerald-500'
                      }`}
                      style={{ width: `${pct}%` }}
                    />
                    <div className="absolute inset-0 flex items-center px-2 font-mono text-slate-100">
                      {b.count} {b.count > 0 && (
                        <span className="text-slate-400 ml-2">
                          {fmtCurrency(b.total_pnl)}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
          <div className="space-y-2 text-xs">
            <KV label="Total trades" value={String(data.total_trades)} />
            <KV label="Total PnL" value={fmtCurrency(data.total_pnl)} />
            <KV
              label="PnL promedio"
              value={fmtCurrency(data.avg_pnl)}
              accent={data.avg_pnl >= 1 ? 'text-emerald-400' : 'text-amber-400'}
            />
            <KV label="Mediana" value={fmtCurrency(data.median_pnl)} />
            <KV
              label="% en pérdida"
              value={`${data.pct_negative.toFixed(1)}%`}
              accent={data.pct_negative > 5 ? 'text-rose-400' : ''}
            />
            <KV
              label="% micro-wins"
              value={`${data.pct_below_threshold.toFixed(1)}%`}
              accent={data.pct_below_threshold > 12 ? 'text-amber-400' : ''}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

function KV({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div className="flex justify-between items-baseline">
      <span className="text-slate-500">{label}</span>
      <span className={`font-mono font-semibold ${accent || 'text-slate-100'}`}>{value}</span>
    </div>
  );
}

function PostmortemTable({ data }: { data: TradePostmortemResponse }) {
  if (!data.items.length) {
    return null;
  }
  // Más reciente primero
  const ordered = [...data.items].reverse();
  const sum = data.summary;

  return (
    <div>
      <h2 className="text-sm uppercase tracking-wider text-slate-400 mb-2">
        Postmortem por trade · ¿vendiste demasiado pronto?
      </h2>
      <p className="text-xs text-slate-500 mb-2">
        Lookahead {sum.lookahead_hours}h · Avg missed {(sum.avg_missed_pct ?? 0).toFixed(2)}% ·{' '}
        Mediana {(sum.median_missed_pct ?? 0).toFixed(2)}% · Max{' '}
        {(sum.max_missed_pct ?? 0).toFixed(2)}%
      </p>
      <div className="overflow-x-auto rounded-lg border border-slate-800 max-h-96 overflow-y-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-900/80 text-slate-400 text-xs uppercase tracking-wider sticky top-0">
            <tr>
              <th className="text-left px-3 py-2">Cuándo</th>
              <th className="text-left px-3 py-2">Acción</th>
              <th className="text-right px-3 py-2">Vendido a</th>
              <th className="text-right px-3 py-2">PnL</th>
              <th className="text-right px-3 py-2">Max después</th>
              <th className="text-right px-3 py-2">Missed</th>
              <th className="text-right px-3 py-2">Drop evitado</th>
            </tr>
          </thead>
          <tbody className="bg-slate-950/40 divide-y divide-slate-800">
            {ordered.map((it, i) => {
              const missed = it.missed_pct;
              const drop = it.drop_pct;
              const significant = missed !== null && missed > 1.0;
              return (
                <tr
                  key={`${it.timestamp}-${i}`}
                  className={significant ? 'bg-amber-950/15' : 'hover:bg-slate-900/40'}
                >
                  <td className="px-3 py-1.5 font-mono text-xs">
                    {it.timestamp.slice(0, 19).replace('T', ' ')}
                  </td>
                  <td className="px-3 py-1.5 text-xs">{it.action}</td>
                  <td className="px-3 py-1.5 text-right">{fmtCurrency(it.sell_price, 0)}</td>
                  <td
                    className={`px-3 py-1.5 text-right ${
                      it.pnl != null && it.pnl > 0
                        ? 'text-emerald-400'
                        : it.pnl != null && it.pnl < 0
                        ? 'text-rose-400'
                        : 'text-slate-500'
                    }`}
                  >
                    {it.pnl != null ? fmtCurrency(it.pnl) : '—'}
                  </td>
                  <td className="px-3 py-1.5 text-right">
                    {it.max_price_after ? fmtCurrency(it.max_price_after, 0) : '—'}
                  </td>
                  <td
                    className={`px-3 py-1.5 text-right font-medium ${
                      missed !== null && missed > 1.0
                        ? 'text-amber-400'
                        : missed !== null && missed > 0.5
                        ? 'text-slate-200'
                        : 'text-slate-500'
                    }`}
                  >
                    {missed !== null ? `+${missed.toFixed(2)}%` : '—'}
                  </td>
                  <td
                    className={`px-3 py-1.5 text-right text-xs ${
                      drop !== null && drop > 0.3 ? 'text-emerald-400' : 'text-slate-500'
                    }`}
                  >
                    {drop !== null ? `${drop >= 0 ? '+' : ''}${drop.toFixed(2)}%` : '—'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-slate-500 mt-1">
        🟡 Filas resaltadas: missed gain &gt;1% — pudo haberse esperado.{' '}
        Drop evitado positivo = la venta fue buena (precio bajó después).
      </p>
    </div>
  );
}

function VetoTable({ data }: { data: VetoPostmortemResponse }) {
  if (!data.items.length) {
    return (
      <div>
        <h2 className="text-sm uppercase tracking-wider text-slate-400 mb-2">
          Postmortem de vetos del Risk Guardian
        </h2>
        <div className="text-sm text-slate-500 italic bg-slate-900/40 border border-slate-800 rounded p-3">
          Sin vetos en el periodo.
        </div>
      </div>
    );
  }

  const ordered = [...data.items].reverse();
  const sum = data.summary;

  return (
    <div>
      <h2 className="text-sm uppercase tracking-wider text-slate-400 mb-2">
        Postmortem de vetos · ¿bloqueamos compras buenas?
      </h2>
      <p className="text-xs text-slate-500 mb-2">
        Total vetos: {sum.total_vetos} · Hubieran sido rentables (≥0.4% en 1h):{' '}
        <span
          className={
            (sum.profitable_pct ?? 0) > 40 ? 'text-amber-400 font-semibold' : 'text-slate-300'
          }
        >
          {sum.profitable_count} ({(sum.profitable_pct ?? 0).toFixed(1)}%)
        </span>
        {sum.by_type && (
          <span className="ml-3">
            Tipos:{' '}
            {Object.entries(sum.by_type)
              .map(([k, v]) => `${k}:${v}`)
              .join(' · ')}
          </span>
        )}
      </p>
      <div className="overflow-x-auto rounded-lg border border-slate-800 max-h-80 overflow-y-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-900/80 text-slate-400 text-xs uppercase tracking-wider sticky top-0">
            <tr>
              <th className="text-left px-3 py-2">Cuándo</th>
              <th className="text-left px-3 py-2">Tipo</th>
              <th className="text-right px-3 py-2">Precio</th>
              <th className="text-right px-3 py-2">Ret. 1h</th>
              <th className="text-right px-3 py-2">Ret. 4h</th>
              <th className="text-left px-3 py-2">Razón</th>
            </tr>
          </thead>
          <tbody className="bg-slate-950/40 divide-y divide-slate-800">
            {ordered.map((v, i) => {
              const r1 = v.return_1h_pct;
              const r4 = v.return_4h_pct;
              return (
                <tr
                  key={`${v.timestamp}-${i}`}
                  className={v.would_have_been_profitable ? 'bg-amber-950/10' : 'hover:bg-slate-900/40'}
                >
                  <td className="px-3 py-1.5 font-mono text-xs">
                    {v.timestamp.slice(0, 19).replace('T', ' ')}
                  </td>
                  <td className="px-3 py-1.5 text-xs">{v.veto_type}</td>
                  <td className="px-3 py-1.5 text-right">{fmtCurrency(v.blocked_price, 0)}</td>
                  <td
                    className={`px-3 py-1.5 text-right text-xs ${
                      r1 !== null && r1 >= 0.4
                        ? 'text-amber-400'
                        : r1 !== null && r1 < 0
                        ? 'text-emerald-400'
                        : 'text-slate-500'
                    }`}
                  >
                    {r1 !== null ? `${r1 >= 0 ? '+' : ''}${r1.toFixed(2)}%` : '—'}
                  </td>
                  <td
                    className={`px-3 py-1.5 text-right text-xs ${
                      r4 !== null && r4 >= 0 ? 'text-slate-200' : 'text-slate-500'
                    }`}
                  >
                    {r4 !== null ? `${r4 >= 0 ? '+' : ''}${r4.toFixed(2)}%` : '—'}
                  </td>
                  <td className="px-3 py-1.5 text-xs text-slate-400 truncate max-w-md">
                    {v.reason}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-slate-500 mt-1">
        🟡 Filas resaltadas: hubieran sido rentables (≥0.4% en 1h). 🟢 Verde 1h: el veto evitó
        una compra perdedora.
      </p>
    </div>
  );
}
