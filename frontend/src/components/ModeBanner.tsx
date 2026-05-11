import { useBotStore } from '../store/botStore';

interface Props {
  onCancelInstruction?: () => void;
}

export function ModeBanner({ onCancelInstruction }: Props) {
  const mode = useBotStore((s) => s.mode);
  const activeInstructionId = useBotStore((s) => s.activeInstructionId);
  const instructions = useBotStore((s) => s.instructions);
  const wsConnected = useBotStore((s) => s.wsConnected);

  const isInstruction = mode === 'INSTRUCTION';
  const active = isInstruction
    ? instructions.find((i) => i.id === activeInstructionId)
    : null;

  return (
    <div
      className={`sticky top-0 z-30 border-b shadow-lg ${
        isInstruction
          ? 'bg-gradient-to-r from-orange-500/90 to-amber-500/90 border-orange-300/40'
          : 'bg-slate-800/90 border-slate-700'
      }`}
    >
      <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between gap-4">
        <div className="flex items-center gap-3 min-w-0">
          <div
            className={`flex items-center gap-2 font-semibold text-sm uppercase tracking-wider ${
              isInstruction ? 'text-white' : 'text-emerald-300'
            }`}
          >
            <span
              className={`inline-block w-2.5 h-2.5 rounded-full ${
                isInstruction ? 'bg-white animate-pulse' : 'bg-emerald-400'
              }`}
            />
            {isInstruction ? 'Modo Instrucción' : 'Modo Normal'}
          </div>
          <div className="text-sm text-slate-200 truncate">
            {isInstruction ? (
              <span>
                Ejecutando: <span className="font-medium">{active?.raw_text || activeInstructionId}</span>
              </span>
            ) : (
              <span className="text-slate-400">
                Reglas duras + agente IA · Las instrucciones del usuario priman cuando se activan
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-3 flex-shrink-0">
          <span
            className={`text-xs px-2 py-1 rounded-full ${
              wsConnected ? 'bg-emerald-900/50 text-emerald-300' : 'bg-red-900/50 text-red-300'
            }`}
            title={wsConnected ? 'WebSocket conectado' : 'Reconectando...'}
          >
            {wsConnected ? '● Live' : '○ Off'}
          </span>
          {isInstruction && onCancelInstruction && (
            <button
              onClick={onCancelInstruction}
              className="text-xs bg-white/20 hover:bg-white/30 text-white px-3 py-1.5 rounded-md font-medium transition"
            >
              Cancelar y volver a Modo Normal
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
