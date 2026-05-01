import { useEffect } from 'react';
import { api } from '../api/client';
import { PnLCard } from '../components/PnLCard';
import { PositionsTable } from '../components/PositionsTable';
import { PriceChart } from '../components/PriceChart';
import { RegimeBadge } from '../components/RegimeBadge';
import { TradesTable } from '../components/TradesTable';
import { useBotStore } from '../store/botStore';

export function DashboardPage() {
  const dashboard = useBotStore((s) => s.dashboard);
  const setDashboard = useBotStore((s) => s.setDashboard);

  useEffect(() => {
    let alive = true;

    async function fetchInitial() {
      try {
        const d = await api.dashboard();
        if (alive) setDashboard(d);
      } catch (err) {
        console.error('No se pudo cargar el dashboard inicial:', err);
      }
    }

    fetchInitial();

    // Refresh periódico (positions/trades no llegan por WS aún)
    const id = setInterval(fetchInitial, 15000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [setDashboard]);

  if (!dashboard) {
    return (
      <div className="text-center text-slate-500 py-16">
        Cargando estado del bot...
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-semibold text-slate-100">Dashboard</h1>
          <RegimeBadge regime={dashboard.regime} confidence={dashboard.regime_confidence} />
          {dashboard.cooldown_active && (
            <span className="text-xs px-2 py-0.5 rounded bg-amber-900/40 text-amber-300 border border-amber-600/30">
              Cooldown activo
            </span>
          )}
        </div>
        <div className="text-xs text-slate-500">
          Uptime: {(dashboard.uptime_s / 60).toFixed(1)} min
        </div>
      </div>

      <PnLCard snap={dashboard} />

      <PriceChart />

      <section>
        <h2 className="text-sm uppercase tracking-wider text-slate-400 mb-2">Posiciones abiertas</h2>
        <PositionsTable positions={dashboard.positions} />
      </section>

      <section>
        <h2 className="text-sm uppercase tracking-wider text-slate-400 mb-2">Trades recientes</h2>
        <TradesTable trades={dashboard.recent_trades} />
      </section>

      <section>
        <h2 className="text-sm uppercase tracking-wider text-slate-400 mb-2">Decisiones del agente recientes</h2>
        <div className="bg-slate-900/40 border border-slate-800 rounded-lg p-3 max-h-64 overflow-y-auto">
          {dashboard.recent_decisions.length === 0 ? (
            <div className="text-sm text-slate-500 italic">Sin decisiones registradas.</div>
          ) : (
            <ul className="space-y-1.5 text-sm">
              {[...dashboard.recent_decisions].reverse().map((d, i) => (
                <li key={i} className="font-mono text-xs">
                  <span className="text-slate-500">{(d.timestamp || '').slice(11, 19)}</span>{' '}
                  <span className="text-slate-300">[{d.source}]</span>{' '}
                  <span className="text-amber-300 font-semibold">{d.action}</span>{' '}
                  <span className="text-slate-400">{d.reasoning}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>
    </div>
  );
}
