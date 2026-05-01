import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { ConfigOut, ConfigSaveResponse } from '../api/types';

export function ConfigPage() {
  const [cfg, setCfg] = useState<ConfigOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [restartHint, setRestartHint] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api.getConfig()
      .then((c) => alive && setCfg(c))
      .catch((e) => alive && setErr(String(e)))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, []);

  async function save(changes: Record<string, unknown>) {
    setSaving(true);
    setErr(null);
    try {
      const resp: ConfigSaveResponse = await api.updateConfig(changes);
      setCfg(resp.config);
      setRestartHint(resp.requires_restart ? resp.restart_reason : null);
    } catch (e) {
      setErr(String(e));
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <div className="text-slate-500">Cargando configuración...</div>;
  if (!cfg) return <div className="text-rose-300">{err || 'No se pudo cargar la configuración.'}</div>;

  return (
    <div className="space-y-5 max-w-3xl">
      <h1 className="text-xl font-semibold text-slate-100">Configuración</h1>

      {err && (
        <div className="bg-rose-900/40 border border-rose-700/50 text-rose-300 text-sm rounded-md px-3 py-2">
          {err}
        </div>
      )}

      {restartHint && (
        <div className="bg-amber-900/40 border border-amber-600/50 text-amber-200 text-sm rounded-md px-3 py-2">
          ⚠️ {restartHint}. Reinicia <code className="bg-black/40 px-1 rounded">python main.py</code> para aplicar.
        </div>
      )}

      <Section title="Proveedores de IA">
        {cfg.providers.map((p) => (
          <ProviderRow
            key={p.name}
            name={p.name}
            enabled={p.enabled}
            keyPreview={p.key_preview}
            onSave={(value) => save(providerEnvKey(p.name, value))}
            saving={saving}
          />
        ))}
        <FieldRow label="Modelo del agente" hint="primary | shadow | full">
          <SelectField
            value={cfg.agent_mode}
            options={['primary', 'shadow', 'full']}
            onSave={(v) => save({ agent_mode: v })}
            saving={saving}
          />
        </FieldRow>
        <FieldRow label="Modelo concreto" hint="ej: gemini-2.0-flash">
          <TextField value={cfg.agent_model} onSave={(v) => save({ agent_model: v })} saving={saving} />
        </FieldRow>
      </Section>

      <Section title="Binance">
        <FieldRow label="API Key" hint={cfg.binance_api_key_preview || 'sin configurar'}>
          <SecretField onSave={(v) => save({ binance_api_key: v })} saving={saving} />
        </FieldRow>
        <FieldRow label="Secret" hint={cfg.binance_secret_preview || 'sin configurar'}>
          <SecretField onSave={(v) => save({ binance_secret: v })} saving={saving} />
        </FieldRow>
        <FieldRow label="Modo Producción" hint="Si OFF usa la API demo de Binance">
          <BoolField value={cfg.prod_mode} onSave={(v) => save({ prod_mode: v })} saving={saving} />
        </FieldRow>
      </Section>

      <Section title="Parámetros de trading">
        <FieldRow label="PAUSA (segundos por ciclo)" hint="default 30">
          <NumberField value={cfg.pausa} step={1} onSave={(v) => save({ pausa: v })} saving={saving} />
        </FieldRow>
        <FieldRow label="Capital por slot" hint="USDT mínimo antes de añadir otra posición">
          <NumberField value={cfg.capital_per_slot} step={50} onSave={(v) => save({ capital_per_slot: v })} saving={saving} />
        </FieldRow>
        <FieldRow label="Capital mínimo posición" hint="USDT para abrir">
          <NumberField value={cfg.min_position_capital} step={10} onSave={(v) => save({ min_position_capital: v })} saving={saving} />
        </FieldRow>
      </Section>
    </div>
  );
}

function providerEnvKey(name: string, value: string): Record<string, unknown> {
  switch (name) {
    case 'gemini':
      return { google_api_key: value };
    case 'claude':
      return { anthropic_api_key: value };
    case 'openai':
      return { openai_api_key: value };
    default:
      return {};
  }
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-slate-900/40 border border-slate-800 rounded-lg overflow-hidden">
      <div className="px-4 py-2 border-b border-slate-800 bg-slate-900/60 text-sm font-semibold uppercase tracking-wider text-slate-300">
        {title}
      </div>
      <div className="p-4 space-y-3">{children}</div>
    </div>
  );
}

function FieldRow({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-center">
      <div>
        <div className="text-sm text-slate-200">{label}</div>
        {hint && <div className="text-xs text-slate-500">{hint}</div>}
      </div>
      <div className="md:col-span-2">{children}</div>
    </div>
  );
}

function ProviderRow({
  name,
  enabled,
  keyPreview,
  onSave,
  saving,
}: {
  name: string;
  enabled: boolean;
  keyPreview: string;
  onSave: (value: string) => void;
  saving: boolean;
}) {
  return (
    <FieldRow
      label={`${name.charAt(0).toUpperCase() + name.slice(1)} ${enabled ? '✓' : ''}`}
      hint={keyPreview || 'sin configurar'}
    >
      <SecretField onSave={onSave} saving={saving} placeholder="Pegar nueva API key..." />
    </FieldRow>
  );
}

function TextField({ value, onSave, saving }: { value: string; onSave: (v: string) => void; saving: boolean }) {
  const [v, setV] = useState(value);
  return (
    <div className="flex gap-2">
      <input
        type="text"
        value={v}
        onChange={(e) => setV(e.target.value)}
        className="flex-1 bg-slate-950 border border-slate-700 rounded-md px-3 py-1.5 text-sm text-slate-100 focus:outline-none focus:border-orange-500"
      />
      <button
        onClick={() => onSave(v)}
        disabled={saving || v === value}
        className="bg-slate-700 hover:bg-slate-600 disabled:opacity-50 px-3 py-1.5 rounded-md text-sm"
      >
        Guardar
      </button>
    </div>
  );
}

function NumberField({ value, step, onSave, saving }: { value: number; step?: number; onSave: (v: number) => void; saving: boolean }) {
  const [v, setV] = useState(value.toString());
  return (
    <div className="flex gap-2">
      <input
        type="number"
        step={step}
        value={v}
        onChange={(e) => setV(e.target.value)}
        className="flex-1 bg-slate-950 border border-slate-700 rounded-md px-3 py-1.5 text-sm text-slate-100 focus:outline-none focus:border-orange-500"
      />
      <button
        onClick={() => onSave(Number(v))}
        disabled={saving || Number(v) === value}
        className="bg-slate-700 hover:bg-slate-600 disabled:opacity-50 px-3 py-1.5 rounded-md text-sm"
      >
        Guardar
      </button>
    </div>
  );
}

function SecretField({ onSave, saving, placeholder }: { onSave: (v: string) => void; saving: boolean; placeholder?: string }) {
  const [v, setV] = useState('');
  return (
    <div className="flex gap-2">
      <input
        type="password"
        value={v}
        onChange={(e) => setV(e.target.value)}
        placeholder={placeholder || 'Nueva clave...'}
        className="flex-1 bg-slate-950 border border-slate-700 rounded-md px-3 py-1.5 text-sm text-slate-100 focus:outline-none focus:border-orange-500"
      />
      <button
        onClick={() => {
          if (v) {
            onSave(v);
            setV('');
          }
        }}
        disabled={saving || !v}
        className="bg-slate-700 hover:bg-slate-600 disabled:opacity-50 px-3 py-1.5 rounded-md text-sm"
      >
        Guardar
      </button>
    </div>
  );
}

function BoolField({ value, onSave, saving }: { value: boolean; onSave: (v: boolean) => void; saving: boolean }) {
  return (
    <div className="flex items-center gap-3">
      <button
        onClick={() => onSave(!value)}
        disabled={saving}
        className={`px-3 py-1.5 rounded-md text-sm font-medium ${
          value
            ? 'bg-emerald-700/60 hover:bg-emerald-600 text-white'
            : 'bg-slate-700 hover:bg-slate-600 text-slate-200'
        }`}
      >
        {value ? '✓ ACTIVO (PROD)' : '○ DEMO'}
      </button>
    </div>
  );
}

function SelectField({
  value,
  options,
  onSave,
  saving,
}: {
  value: string;
  options: string[];
  onSave: (v: string) => void;
  saving: boolean;
}) {
  return (
    <div className="flex gap-2">
      <select
        value={value}
        onChange={(e) => onSave(e.target.value)}
        disabled={saving}
        className="flex-1 bg-slate-950 border border-slate-700 rounded-md px-3 py-1.5 text-sm text-slate-100 focus:outline-none focus:border-orange-500"
      >
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </div>
  );
}
