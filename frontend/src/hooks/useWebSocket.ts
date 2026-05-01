import { useEffect, useRef } from 'react';
import { useBotStore } from '../store/botStore';
import type { WSEvent } from '../api/types';

const RECONNECT_BASE_MS = 1000;
const RECONNECT_MAX_MS = 15000;

export function useBotWebSocket() {
  const setWsConnected = useBotStore((s) => s.setWsConnected);
  const applyTick = useBotStore((s) => s.applyTick);
  const setMode = useBotStore((s) => s.setMode);
  const setRestart = useBotStore((s) => s.setRestart);

  const wsRef = useRef<WebSocket | null>(null);
  const retryRef = useRef(0);
  const closedByUserRef = useRef(false);

  useEffect(() => {
    closedByUserRef.current = false;

    function connect() {
      const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
      const url = `${proto}://${window.location.host}/ws/stream`;
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        setWsConnected(true);
        // Si estábamos en estado "reiniciando" y volvió la conexión, asumimos
        // que el bot terminó de reiniciar y ya está operando con los nuevos
        // parámetros (incluyendo reconciliación de saldos).
        const prev = useBotStore.getState().restart;
        if (prev.scheduled) {
          setRestart({ scheduled: false, reason: '', requestedAt: 0 });
        }
        retryRef.current = 0;
      };

      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data) as WSEvent;
          switch (msg.type) {
            case 'tick':
              applyTick(msg.data);
              break;
            case 'mode_changed':
              setMode(msg.data.mode, msg.data.active_instruction_id);
              break;
            case 'restart_requested':
              setRestart({
                scheduled: true,
                reason: msg.data.reason,
                requestedAt: msg.data.requested_at,
              });
              break;
            case 'instruction_event':
            case 'trade_executed':
            case 'position_change':
              // El próximo polling refrescará los datos;
              // los listeners de InstructionsPage también pueden refrescar.
              window.dispatchEvent(new CustomEvent('bot:ws', { detail: msg }));
              break;
          }
        } catch {
          // ignore
        }
      };

      ws.onclose = () => {
        setWsConnected(false);
        if (closedByUserRef.current) return;
        const delay = Math.min(
          RECONNECT_BASE_MS * 2 ** retryRef.current,
          RECONNECT_MAX_MS
        );
        retryRef.current += 1;
        setTimeout(connect, delay);
      };

      ws.onerror = () => {
        try {
          ws.close();
        } catch {
          // ignore
        }
      };
    }

    connect();

    return () => {
      closedByUserRef.current = true;
      try {
        wsRef.current?.close();
      } catch {
        // ignore
      }
    };
  }, [applyTick, setMode, setWsConnected]);
}
