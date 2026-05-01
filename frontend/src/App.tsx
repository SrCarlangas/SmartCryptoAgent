import { useEffect, useState } from 'react';
import { api } from './api/client';
import { ModeBanner } from './components/ModeBanner';
import { useBotWebSocket } from './hooks/useWebSocket';
import { ConfigPage } from './pages/ConfigPage';
import { DashboardPage } from './pages/DashboardPage';
import { InstructionsPage } from './pages/InstructionsPage';
import { useBotStore } from './store/botStore';

type Tab = 'dashboard' | 'instructions' | 'config';

const TABS: { id: Tab; label: string }[] = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'instructions', label: 'Instrucciones' },
  { id: 'config', label: 'Configuración' },
];

export default function App() {
  const [tab, setTab] = useState<Tab>('dashboard');
  const setInstructions = useBotStore((s) => s.setInstructions);
  const setMode = useBotStore((s) => s.setMode);
  useBotWebSocket();

  useEffect(() => {
    api
      .listInstructions()
      .then((list) => {
        setInstructions(list);
        const active = list.find(
          (i) => i.status === 'active' || i.status === 'triggered'
        );
        setMode(active ? 'INSTRUCTION' : 'NORMAL', active?.id ?? null);
      })
      .catch(() => {
        // ignore on first paint
      });
  }, [setInstructions, setMode]);

  async function cancelActive() {
    const active = useBotStore
      .getState()
      .instructions.find(
        (i) => i.status === 'active' || i.status === 'triggered'
      );
    if (!active) return;
    await api.cancelInstruction(active.id);
    const refreshed = await api.listInstructions();
    setInstructions(refreshed);
    setMode('NORMAL', null);
  }

  return (
    <div className="min-h-screen flex flex-col">
      <ModeBanner onCancelInstruction={cancelActive} />

      <header className="border-b border-slate-800 bg-slate-900/40">
        <div className="max-w-7xl mx-auto px-4 py-2 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-lg">🤖</span>
            <span className="font-semibold text-slate-100">SmartCryptoAgent</span>
            <span className="text-xs text-slate-500">Panel de control</span>
          </div>
          <nav className="flex gap-1">
            {TABS.map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={`px-3 py-1.5 rounded-md text-sm font-medium transition ${
                  tab === t.id
                    ? 'bg-slate-700 text-white'
                    : 'text-slate-300 hover:bg-slate-800'
                }`}
              >
                {t.label}
              </button>
            ))}
          </nav>
        </div>
      </header>

      <main className="flex-1 max-w-7xl mx-auto w-full px-4 py-5">
        {tab === 'dashboard' && <DashboardPage />}
        {tab === 'instructions' && <InstructionsPage />}
        {tab === 'config' && <ConfigPage />}
      </main>

      <footer className="border-t border-slate-800 text-xs text-slate-500 text-center py-3">
        Bot privado · Bind 127.0.0.1 · No publicado
      </footer>
    </div>
  );
}
