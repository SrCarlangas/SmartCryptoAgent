import { useEffect, useMemo, useState } from 'react';
import { api } from '../api/client';
import type {
  ParameterCategoryOut,
  ParameterUpdateIn,
  ParameterValueOut,
  ParametersResponse,
} from '../api/types';

export function ParametersPage() {
  const [data, setData] = useState<ParametersResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [edits, setEdits] = useState<Record<string, number | string | boolean>>({});
  const [saving, setSaving] = useState(false);
  const [savedFlash, setSavedFlash] = useState<string | null>(null);
  const [activeCategory, setActiveCategory] = useState<string>('trading');

  async function reload() {
    setLoading(true);
    setErr(null);
    try {
      const d = await api.getParameters();
      setData(d);
      setEdits({});
    } catch (e) {
      setErr(String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    reload();
  }, []);

  const grouped = useMemo(() => {
    if (!data) return new Map<string, ParameterValueOut[]>();
    const m = new Map<string, ParameterValueOut[]>();
    for (const p of data.parameters) {
      if (!m.has(p.category)) m.set(p.category, []);
      m.get(p.category)!.push(p);
    }
    return m;
  }, [data]);

  function setEdit(key: string, value: number | string | boolean) {
    setEdits((prev) => ({ ...prev, [key]: value }));
  }

  function clearEdit(key: string) {
    setEdits((prev) => {
      const n = { ...prev };
      delete n[key];
      return n;
    });
  }

  async function saveAll() {
    if (Object.keys(edits).length === 0) return;
    setSaving(true);
    setErr(null);
    try {
      const updates: ParameterUpdateIn[] = Object.entries(edits).map(([key, value]) => ({
        key,
        value,
      }));
      const resp = await api.updateParameters(updates);
      const okCount = resp.saved.length;
      const errCount = Object.keys(resp.errors).length;
      let flash = `${okCount} parámetro${okCount === 1 ? '' : 's'} guardado${okCount === 1 ? '' : 's'}`;
      if (resp.restart_scheduled) {
        flash += ` · reinicio programado (≤${resp.restart_in_seconds_max}s)`;
      }
      if (errCount > 0) {
        flash += ` · ${errCount} con error`;
      }
      setSavedFlash(flash);
      setTimeout(() => setSavedFlash(null), 6000);
      // Refrescar (current_value, is_overridden) y limpiar edits aplicados
      await reload();
      // Mostrar errores si hubo
      if (errCount > 0) {
        const summary = Object.entries(resp.errors)
          .map(([k, v]) => `${k}: ${v}`)
          .join('; ');
        setErr(summary);
      }
    } catch (e) {
      setErr(String(e));
    } finally {
      setSaving(false);
    }
  }

  async function resetParam(key: string) {
    setSaving(true);
    setErr(null);
    try {
      await api.resetParameter(key);
      await reload();
      setSavedFlash(`${key} restaurado al default · reinicio programado`);
      setTimeout(() => setSavedFlash(null), 6000);
    } catch (e) {
      setErr(String(e));
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <div className="text-slate-500">Cargando parámetros...</div>;
  if (!data) return <div className="text-rose-300">{err || 'No se pudo cargar.'}</div>;

  const categories = data.categories;
  const dirty = Object.keys(edits).length > 0;

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">Parámetros del bot</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Editar y guardar dispara reinicio automático del bot al inicio del próximo ciclo.
            El reinicio re-ejecuta <code className="bg-black/40 px-1 rounded">main.py</code> y
            llama <code className="bg-black/40 px-1 rounded">reconciliar_estado()</code> con saldos reales.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {savedFlash && (
            <span className="text-xs text-emerald-300 bg-emerald-900/30 border border-emerald-700/30 rounded px-2 py-1">
              ✓ {savedFlash}
            </span>
          )}
          <button
            onClick={saveAll}
            disabled={!dirty || saving}
            className="bg-orange-600 hover:bg-orange-500 disabled:opacity-40 text-white px-4 py-1.5 rounded-md text-sm font-medium"
          >
            {saving ? 'Guardando...' : `Guardar y reiniciar${dirty ? ` (${Object.keys(edits).length})` : ''}`}
          </button>
          <button
            onClick={() => setEdits({})}
            disabled={!dirty || saving}
            className="text-slate-400 hover:text-slate-200 disabled:opacity-40 text-sm"
          >
            Descartar
          </button>
        </div>
      </div>

      {err && (
        <div className="bg-rose-900/40 border border-rose-700/50 text-rose-300 text-sm rounded-md px-3 py-2">
          {err}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-[200px_1fr] gap-5">
        <aside className="lg:sticky lg:top-32 self-start">
          <ul className="bg-slate-900/40 border border-slate-800 rounded-lg overflow-hidden">
            {categories.map((c) => {
              const params = grouped.get(c.id) || [];
              const overrides = params.filter((p) => p.is_overridden).length;
              const dirtyHere = params.filter((p) => p.key in edits).length;
              return (
                <li key={c.id}>
                  <button
                    onClick={() => setActiveCategory(c.id)}
                    className={`w-full text-left px-3 py-2 text-sm flex items-center justify-between transition ${
                      activeCategory === c.id
                        ? 'bg-slate-800 text-white'
                        : 'text-slate-300 hover:bg-slate-800/50'
                    }`}
                  >
                    <span>
                      {c.icon} {c.label}
                    </span>
                    <span className="text-xs">
                      {dirtyHere > 0 ? (
                        <span className="text-orange-400">●{dirtyHere}</span>
                      ) : overrides > 0 ? (
                        <span className="text-slate-500">{overrides}</span>
                      ) : null}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </aside>

        <section className="space-y-3">
          {categories
            .filter((c) => c.id === activeCategory)
            .map((c) => (
              <CategorySection
                key={c.id}
                category={c}
                params={grouped.get(c.id) || []}
                edits={edits}
                onEdit={setEdit}
                onClearEdit={clearEdit}
                onReset={resetParam}
              />
            ))}
        </section>
      </div>
    </div>
  );
}

interface SectionProps {
  category: ParameterCategoryOut;
  params: ParameterValueOut[];
  edits: Record<string, number | string | boolean>;
  onEdit: (key: string, value: number | string | boolean) => void;
  onClearEdit: (key: string) => void;
  onReset: (key: string) => void;
}

function CategorySection({ category, params, edits, onEdit, onClearEdit, onReset }: SectionProps) {
  return (
    <div className="bg-slate-900/40 border border-slate-800 rounded-lg overflow-hidden">
      <div className="px-4 py-2 border-b border-slate-800 bg-slate-900/60 text-sm font-semibold uppercase tracking-wider text-slate-300">
        {category.icon} {category.label}
      </div>
      <div className="divide-y divide-slate-800">
        {params.map((p) => (
          <ParameterRow
            key={p.key}
            param={p}
            editValue={edits[p.key]}
            onEdit={onEdit}
            onClearEdit={onClearEdit}
            onReset={onReset}
          />
        ))}
      </div>
    </div>
  );
}

interface RowProps {
  param: ParameterValueOut;
  editValue: number | string | boolean | undefined;
  onEdit: (key: string, value: number | string | boolean) => void;
  onClearEdit: (key: string) => void;
  onReset: (key: string) => void;
}

function ParameterRow({ param, editValue, onEdit, onClearEdit, onReset }: RowProps) {
  const isDirty = editValue !== undefined;
  const displayValue = isDirty ? editValue : param.current_display;

  const minDisplay = param.min ?? undefined;
  const maxDisplay = param.max ?? undefined;
  const stepDisplay = param.step ?? undefined;

  function handleChange(raw: string) {
    if (param.type === 'int') {
      const v = raw === '' ? '' : Math.round(Number(raw));
      onEdit(param.key, v as number);
    } else if (param.type === 'float' || param.type === 'percent') {
      onEdit(param.key, raw === '' ? 0 : Number(raw));
    } else if (param.type === 'bool') {
      onEdit(param.key, raw === 'true');
    } else {
      onEdit(param.key, raw);
    }
  }

  return (
    <div className="px-4 py-3 grid grid-cols-1 md:grid-cols-[1fr_auto] gap-3 items-start">
      <div className="min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <code className="text-xs bg-slate-950 border border-slate-800 px-1.5 py-0.5 rounded text-slate-400">
            {param.key}
          </code>
          <span className="text-sm text-slate-100 font-medium">{param.label}</span>
          {param.is_overridden && !isDirty && (
            <span className="text-[10px] uppercase tracking-wider text-amber-400 bg-amber-900/20 border border-amber-700/30 px-1.5 py-0.5 rounded">
              override
            </span>
          )}
          {isDirty && (
            <span className="text-[10px] uppercase tracking-wider text-orange-300 bg-orange-900/30 border border-orange-700/40 px-1.5 py-0.5 rounded">
              modificado
            </span>
          )}
        </div>
        <p className="text-xs text-slate-400 mt-1 leading-relaxed">{param.description}</p>
        <div className="text-[11px] text-slate-500 mt-1 font-mono">
          default: {String(typeof param.default === 'number' && param.type === 'percent' ? `${(Number(param.default) * 100).toFixed(2)}%` : param.default)}
          {param.unit ? ` · unidad: ${param.unit}` : ''}
          {param.type === 'percent' ? ' · (mostrado en %)' : ''}
        </div>
      </div>
      <div className="flex flex-col gap-1.5 items-end md:min-w-[260px]">
        <div className="flex gap-2 items-center w-full">
          {param.type === 'bool' ? (
            <select
              value={String(displayValue)}
              onChange={(e) => handleChange(e.target.value)}
              className="flex-1 bg-slate-950 border border-slate-700 rounded-md px-3 py-1.5 text-sm text-slate-100 focus:outline-none focus:border-orange-500"
            >
              <option value="true">Sí</option>
              <option value="false">No</option>
            </select>
          ) : param.type === 'select' ? (
            <select
              value={String(displayValue)}
              onChange={(e) => handleChange(e.target.value)}
              className="flex-1 bg-slate-950 border border-slate-700 rounded-md px-3 py-1.5 text-sm text-slate-100 focus:outline-none focus:border-orange-500"
            >
              {param.options.map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </select>
          ) : (
            <input
              type="number"
              step={stepDisplay}
              min={minDisplay}
              max={maxDisplay}
              value={String(displayValue)}
              onChange={(e) => handleChange(e.target.value)}
              className={`flex-1 bg-slate-950 border rounded-md px-3 py-1.5 text-sm text-slate-100 focus:outline-none focus:border-orange-500 font-mono ${
                isDirty ? 'border-orange-500/60' : 'border-slate-700'
              }`}
            />
          )}
          {param.unit && param.type !== 'percent' && (
            <span className="text-xs text-slate-500">{param.unit}</span>
          )}
          {param.type === 'percent' && <span className="text-xs text-slate-500">%</span>}
        </div>
        <div className="flex gap-2 text-xs">
          {isDirty && (
            <button
              onClick={() => onClearEdit(param.key)}
              className="text-slate-400 hover:text-slate-200"
            >
              cancelar
            </button>
          )}
          {param.is_overridden && !isDirty && (
            <button
              onClick={() => {
                if (confirm(`¿Restaurar ${param.key} a su default y reiniciar el bot?`)) {
                  onReset(param.key);
                }
              }}
              className="text-slate-400 hover:text-rose-300"
            >
              restaurar default
            </button>
          )}
          {minDisplay !== undefined && maxDisplay !== undefined && (
            <span className="text-slate-600">
              [{minDisplay}–{maxDisplay}]
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
