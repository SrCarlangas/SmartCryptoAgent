import type { InstructionOut } from '../api/types';
import { fmtCurrency } from '../utils/format';

interface Props {
  instruction: InstructionOut;
  onCancel: () => void;
}

export function InstructionStatus({ instruction, onCancel }: Props) {
  const i = instruction;
  const created = new Date(i.created_at * 1000).toLocaleString();

  return (
    <div className="bg-gradient-to-r from-orange-950/40 to-amber-950/40 border border-orange-700/40 rounded-lg p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-xs uppercase tracking-wider px-2 py-0.5 rounded bg-orange-500/20 text-orange-300 border border-orange-500/30">
              {i.status}
            </span>
            <span className="text-xs text-slate-400">{created}</span>
          </div>
          <div className="mt-2 text-base text-slate-100">«{i.raw_text}»</div>
          <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
            <Block label="Entrada" entered={i.entered}>
              {i.entry_conditions.length > 0 ? (
                <ul className="font-mono text-xs text-slate-300">
                  {i.entry_conditions.map((c, idx) => (
                    <li key={idx}>· {c.type} {c.operator} {fmtCurrency(c.value, 0)}{c.fired_at > 0 ? ' ✓' : ''}</li>
                  ))}
                </ul>
              ) : <span className="text-slate-500">—</span>}
              {i.entry_action && (
                <div className="text-xs text-slate-400 mt-1">
                  {i.entry_action.type} {i.entry_action.quantity_btc > 0 ? `${i.entry_action.quantity_btc} BTC` : ''}
                  {i.entry_action.quantity_usdt > 0 ? `$${i.entry_action.quantity_usdt} USDT` : ''}
                </div>
              )}
            </Block>
            <Block label="Salida" entered={i.exited}>
              {i.exit_conditions.length > 0 ? (
                <ul className="font-mono text-xs text-slate-300">
                  {i.exit_conditions.map((c, idx) => (
                    <li key={idx}>· {c.type} {c.operator} {fmtCurrency(c.value, 0)}{c.fired_at > 0 ? ' ✓' : ''}</li>
                  ))}
                </ul>
              ) : <span className="text-slate-500">—</span>}
              {i.exit_action && (
                <div className="text-xs text-slate-400 mt-1">
                  {i.exit_action.type} sell_pct={i.exit_action.sell_pct}
                </div>
              )}
            </Block>
          </div>
        </div>
        <button
          onClick={onCancel}
          className="bg-rose-700/80 hover:bg-rose-600 text-white text-xs px-3 py-2 rounded-md flex-shrink-0"
        >
          Cancelar
        </button>
      </div>

      {i.history.length > 0 && (
        <details className="mt-4 text-xs text-slate-400">
          <summary className="cursor-pointer hover:text-slate-200">Historial ({i.history.length})</summary>
          <ul className="mt-1 space-y-0.5 font-mono">
            {i.history.slice().reverse().map((h, idx) => (
              <li key={idx}>
                {new Date(h.ts * 1000).toLocaleTimeString()} — <span className="text-slate-300">{h.event}</span>
                {h.details ? <span className="text-slate-500"> · {h.details}</span> : null}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

function Block({ label, entered, children }: { label: string; entered: boolean; children: React.ReactNode }) {
  return (
    <div className={`rounded-md border p-2 ${entered ? 'bg-emerald-900/20 border-emerald-700/40' : 'bg-slate-900/40 border-slate-700/40'}`}>
      <div className="text-xs uppercase tracking-wider text-slate-400 flex items-center gap-2">
        {label}
        {entered && <span className="text-emerald-400">disparada</span>}
      </div>
      <div className="mt-1">{children}</div>
    </div>
  );
}
