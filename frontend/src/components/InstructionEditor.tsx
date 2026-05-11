import { useEffect, useRef, useState } from 'react';
import { api } from '../api/client';
import type { InstructionPreviewOut } from '../api/types';

interface Props {
  onCreated: () => void;
}

const EXAMPLES = [
  'Compra 0.001 BTC si baja a $95000, vende cuando llegue a $98000',
  'Vende todo si baja a $90000',
  'Compra 50 USDT si btc cae a $94000 y vende cuando suba a $96500',
];

export function InstructionEditor({ onCreated }: Props) {
  const [text, setText] = useState('');
  const [complex, setComplex] = useState(false);
  const [preview, setPreview] = useState<InstructionPreviewOut | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [activating, setActivating] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const debounceRef = useRef<number | null>(null);
  const lastPreviewedRef = useRef<string>('');

  // Auto-preview con debounce: a medida que el usuario escribe, después de
  // 600ms sin nuevos cambios, automáticamente ejecuta el preview. Esto
  // resuelve la confusión de UX donde el botón "Activar" parecía "no responder"
  // porque el usuario no sabía que debía hacer preview manual primero.
  useEffect(() => {
    const trimmed = text.trim();
    if (!trimmed) {
      setPreview(null);
      return;
    }
    // Cancela debounce previo
    if (debounceRef.current !== null) {
      window.clearTimeout(debounceRef.current);
    }
    debounceRef.current = window.setTimeout(async () => {
      // Evita re-preview si el texto no cambió desde el último preview
      const key = `${trimmed}|${complex}`;
      if (lastPreviewedRef.current === key) return;
      setPreviewing(true);
      setErr(null);
      try {
        const p = await api.previewInstruction(trimmed, complex);
        setPreview(p);
        lastPreviewedRef.current = key;
      } catch (e) {
        setErr(String(e));
      } finally {
        setPreviewing(false);
      }
    }, 600);
    return () => {
      if (debounceRef.current !== null) {
        window.clearTimeout(debounceRef.current);
      }
    };
  }, [text, complex]);

  async function doPreview() {
    if (!text.trim()) return;
    setPreviewing(true);
    setErr(null);
    try {
      const p = await api.previewInstruction(text, complex);
      setPreview(p);
      lastPreviewedRef.current = `${text.trim()}|${complex}`;
    } catch (e) {
      setErr(String(e));
    } finally {
      setPreviewing(false);
    }
  }

  async function doActivate() {
    if (!text.trim()) return;
    setActivating(true);
    setErr(null);
    try {
      // Si el preview no está listo o está stale, hacerlo ahora antes de activar
      let p = preview;
      const key = `${text.trim()}|${complex}`;
      if (!p || lastPreviewedRef.current !== key) {
        p = await api.previewInstruction(text, complex);
        setPreview(p);
        lastPreviewedRef.current = key;
      }
      if (!p.can_activate) {
        setErr(
          'No se puede activar: ' +
            (p.blocking_warnings.join('; ') ||
              p.parsed.parse_warnings.join('; ') ||
              'instrucción no válida')
        );
        return;
      }
      await api.createInstruction(text, complex);
      setText('');
      setPreview(null);
      lastPreviewedRef.current = '';
      onCreated();
    } catch (e) {
      setErr(String(e));
    } finally {
      setActivating(false);
    }
  }

  return (
    <div className="bg-slate-900/60 border border-slate-800 rounded-lg p-4 space-y-4">
      <div>
        <label className="block text-sm font-medium text-slate-300 mb-1">
          Instrucción al agente (texto libre)
        </label>
        <textarea
          rows={3}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Ej: compra 0.001 BTC si baja a $95000, vende cuando llegue a $98000"
          className="w-full bg-slate-950 border border-slate-700 rounded-md px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-orange-500 resize-y"
        />
        <div className="text-xs text-slate-500 mt-1">
          {previewing ? '⏳ Parseando...' :
           preview?.can_activate ? '✅ Lista para activar' :
           preview && !preview.can_activate ? '⚠️ Revisar avisos abajo' :
           'Empieza a escribir — el parser valida automáticamente cada 600ms'}
        </div>
        <div className="flex flex-wrap gap-2 mt-2">
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              onClick={() => {
                setText(ex);
                setPreview(null);
              }}
              className="text-xs bg-slate-800 hover:bg-slate-700 text-slate-300 px-2 py-1 rounded"
            >
              {ex}
            </button>
          ))}
        </div>
      </div>

      <label className="inline-flex items-center gap-2 text-sm text-slate-400">
        <input
          type="checkbox"
          checked={complex}
          onChange={(e) => setComplex(e.target.checked)}
          className="rounded"
        />
        Marcar como compleja (evaluación LLM por ciclo — aún no disponible)
      </label>

      <div className="flex flex-wrap gap-2 items-center">
        <button
          onClick={doActivate}
          disabled={!text.trim() || activating}
          className="bg-orange-600 hover:bg-orange-500 disabled:opacity-50 text-white px-4 py-2 rounded-md text-sm font-medium"
          title={
            preview?.can_activate
              ? 'Activar instrucción'
              : preview && !preview.can_activate
                ? 'El parser detectó problemas — corregilos abajo'
                : 'Se previsualizará automáticamente al hacer clic'
          }
        >
          {activating ? 'Activando...' : 'Activar instrucción'}
        </button>
        <button
          onClick={doPreview}
          disabled={!text.trim() || previewing}
          className="bg-slate-700 hover:bg-slate-600 disabled:opacity-50 text-slate-100 px-3 py-2 rounded-md text-xs"
        >
          {previewing ? 'Parseando...' : 'Re-previsualizar'}
        </button>
      </div>

      {err && (
        <div className="bg-rose-900/40 border border-rose-700/50 text-rose-300 text-sm rounded-md px-3 py-2">
          {err}
        </div>
      )}

      {preview && <PreviewCard preview={preview} />}
    </div>
  );
}

function PreviewCard({ preview }: { preview: InstructionPreviewOut }) {
  const p = preview.parsed;
  return (
    <div className={`border rounded-lg p-3 ${preview.can_activate ? 'border-emerald-700/40 bg-emerald-950/20' : 'border-amber-700/40 bg-amber-950/20'}`}>
      <div className="text-xs uppercase tracking-wider text-slate-400 mb-2">
        {preview.can_activate ? 'Instrucción parseada — lista para activar' : 'No se puede activar'}
      </div>
      <Section label="Condiciones de entrada" items={p.entry_conditions.map(c => `${c.type} ${c.operator} ${c.value}`)} />
      {p.entry_action && (
        <Section label="Acción de entrada" items={[`${p.entry_action.type} qty_btc=${p.entry_action.quantity_btc} qty_usdt=${p.entry_action.quantity_usdt}`]} />
      )}
      <Section label="Condiciones de salida" items={p.exit_conditions.map(c => `${c.type} ${c.operator} ${c.value}`)} />
      {p.exit_action && (
        <Section label="Acción de salida" items={[`${p.exit_action.type} sell_pct=${p.exit_action.sell_pct}`]} />
      )}
      {p.parse_warnings.length > 0 && (
        <Section label="Avisos del parser" items={p.parse_warnings} accent="text-amber-300" />
      )}
      {preview.blocking_warnings.length > 0 && (
        <Section label="Bloqueos" items={preview.blocking_warnings} accent="text-rose-300" />
      )}
    </div>
  );
}

function Section({ label, items, accent }: { label: string; items: string[]; accent?: string }) {
  if (!items.length) return null;
  return (
    <div className="mb-2">
      <div className="text-xs text-slate-400 mb-1">{label}</div>
      <ul className={`text-sm font-mono ${accent || 'text-slate-200'}`}>
        {items.map((it, i) => (
          <li key={i}>· {it}</li>
        ))}
      </ul>
    </div>
  );
}
