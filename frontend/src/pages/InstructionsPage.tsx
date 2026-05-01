import { useCallback, useEffect, useState } from 'react';
import { api } from '../api/client';
import { InstructionEditor } from '../components/InstructionEditor';
import { InstructionStatus } from '../components/InstructionStatus';
import { useBotStore } from '../store/botStore';

export function InstructionsPage() {
  const instructions = useBotStore((s) => s.instructions);
  const setInstructions = useBotStore((s) => s.setInstructions);
  const setMode = useBotStore((s) => s.setMode);
  const [err, setErr] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const list = await api.listInstructions();
      setInstructions(list);
      const active = list.find((i) => i.status === 'active' || i.status === 'triggered');
      setMode(active ? 'INSTRUCTION' : 'NORMAL', active?.id ?? null);
    } catch (e) {
      setErr(String(e));
    }
  }, [setInstructions, setMode]);

  useEffect(() => {
    reload();
    const onWs = (e: Event) => {
      const ev = (e as CustomEvent).detail as { type: string };
      if (ev.type === 'instruction_event' || ev.type === 'mode_changed') {
        reload();
      }
    };
    window.addEventListener('bot:ws', onWs);
    return () => window.removeEventListener('bot:ws', onWs);
  }, [reload]);

  const active = instructions.find(
    (i) => i.status === 'active' || i.status === 'triggered'
  );
  const history = instructions.filter((i) => i !== active);

  async function cancel(id: string) {
    setErr(null);
    try {
      await api.cancelInstruction(id);
      await reload();
    } catch (e) {
      setErr(String(e));
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-100">Instrucciones</h1>
        <span className="text-xs text-slate-500">
          Una sola instrucción puede estar activa a la vez
        </span>
      </div>

      {err && (
        <div className="bg-rose-900/40 border border-rose-700/50 text-rose-300 text-sm rounded-md px-3 py-2">
          {err}
        </div>
      )}

      {active ? (
        <InstructionStatus instruction={active} onCancel={() => cancel(active.id)} />
      ) : (
        <InstructionEditor onCreated={reload} />
      )}

      <section>
        <h2 className="text-sm uppercase tracking-wider text-slate-400 mb-2">Historial</h2>
        {history.length === 0 ? (
          <div className="text-sm text-slate-500 italic">
            Aún no hay instrucciones en el historial.
          </div>
        ) : (
          <ul className="space-y-2">
            {[...history].sort((a, b) => b.created_at - a.created_at).map((i) => (
              <li key={i.id} className="bg-slate-900/40 border border-slate-800 rounded-md p-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <div className="text-sm text-slate-200 truncate">«{i.raw_text}»</div>
                    <div className="text-xs text-slate-500 mt-0.5 font-mono">
                      {new Date(i.created_at * 1000).toLocaleString()} · id={i.id}
                    </div>
                  </div>
                  <span
                    className={`text-xs px-2 py-1 rounded ${statusColor(i.status)}`}
                  >
                    {i.status}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function statusColor(status: string): string {
  switch (status) {
    case 'completed':
      return 'bg-emerald-900/40 text-emerald-300 border border-emerald-700/30';
    case 'cancelled':
      return 'bg-slate-800 text-slate-400 border border-slate-700';
    case 'failed':
      return 'bg-rose-900/40 text-rose-300 border border-rose-700/30';
    case 'expired':
      return 'bg-amber-900/40 text-amber-300 border border-amber-700/30';
    default:
      return 'bg-slate-800 text-slate-400 border border-slate-700';
  }
}
