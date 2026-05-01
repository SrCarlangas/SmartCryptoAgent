import { useState } from 'react';
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

  async function doPreview() {
    if (!text.trim()) return;
    setPreviewing(true);
    setErr(null);
    setPreview(null);
    try {
      const p = await api.previewInstruction(text, complex);
      setPreview(p);
    } catch (e) {
      setErr(String(e));
    } finally {
      setPreviewing(false);
    }
  }

  async function doActivate() {
    if (!preview?.can_activate) return;
    setActivating(true);
    setErr(null);
    try {
      await api.createInstruction(text, complex);
      setText('');
      setPreview(null);
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
          onChange={(e) => {
            setText(e.target.value);
            setPreview(null);
          }}
          placeholder="Ej: compra 0.001 BTC si baja a $95000, vende cuando llegue a $98000"
          className="w-full bg-slate-950 border border-slate-700 rounded-md px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-orange-500 resize-y"
        />
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
          onChange={(e) => {
            setComplex(e.target.checked);
            setPreview(null);
          }}
          className="rounded"
        />
        Marcar como compleja (evaluación LLM por ciclo — aún no disponible)
      </label>

      <div className="flex flex-wrap gap-2">
        <button
          onClick={doPreview}
          disabled={!text.trim() || previewing}
          className="bg-slate-700 hover:bg-slate-600 disabled:opacity-50 text-slate-100 px-4 py-2 rounded-md text-sm font-medium"
        >
          {previewing ? 'Parseando...' : 'Vista previa'}
        </button>
        <button
          onClick={doActivate}
          disabled={!preview?.can_activate || activating}
          className="bg-orange-600 hover:bg-orange-500 disabled:opacity-50 text-white px-4 py-2 rounded-md text-sm font-medium"
        >
          {activating ? 'Activando...' : 'Activar'}
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
