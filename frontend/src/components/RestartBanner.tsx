import { useEffect, useState } from 'react';
import { useBotStore } from '../store/botStore';

export function RestartBanner() {
  const restart = useBotStore((s) => s.restart);
  const wsConnected = useBotStore((s) => s.wsConnected);
  const [secondsAgo, setSecondsAgo] = useState(0);

  useEffect(() => {
    if (!restart.scheduled) return;
    const t = setInterval(() => {
      setSecondsAgo(Math.floor(Date.now() / 1000 - restart.requestedAt));
    }, 1000);
    return () => clearInterval(t);
  }, [restart.scheduled, restart.requestedAt]);

  if (!restart.scheduled) return null;

  const stage = !wsConnected ? 'restarting' : 'pending';

  return (
    <div className="bg-blue-900/80 border-b border-blue-500/40 text-blue-100 text-sm">
      <div className="max-w-7xl mx-auto px-4 py-2 flex items-center gap-3">
        <span className="inline-block w-2.5 h-2.5 rounded-full bg-blue-400 animate-pulse" />
        {stage === 'pending' ? (
          <>
            <span className="font-semibold">Reinicio programado</span>
            <span className="text-blue-200">— {restart.reason}</span>
            <span className="text-blue-300/80 text-xs ml-auto">
              esperando inicio de próximo ciclo · {secondsAgo}s
            </span>
          </>
        ) : (
          <>
            <span className="font-semibold">Reiniciando bot...</span>
            <span className="text-blue-200">
              recargando configuración y reconciliando saldos
            </span>
            <span className="text-blue-300/80 text-xs ml-auto">
              esperando reconexión...
            </span>
          </>
        )}
      </div>
    </div>
  );
}
