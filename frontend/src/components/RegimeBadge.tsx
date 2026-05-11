interface Props {
  regime: string;
  confidence: number;
}

const COLORS: Record<string, string> = {
  ALCISTA: 'bg-emerald-900/60 text-emerald-300 border-emerald-600/40',
  BAJISTA: 'bg-rose-900/60 text-rose-300 border-rose-600/40',
  LATERAL: 'bg-slate-800 text-slate-300 border-slate-600/40',
  CRASH: 'bg-red-900/80 text-red-200 border-red-500/50 animate-pulse',
};

export function RegimeBadge({ regime, confidence }: Props) {
  const cls = COLORS[regime] || COLORS.LATERAL;
  return (
    <span
      className={`inline-flex items-center gap-2 text-xs font-semibold px-2.5 py-1 rounded-md border ${cls}`}
    >
      {regime}
      <span className="opacity-70">
        {(confidence * 100).toFixed(0)}%
      </span>
    </span>
  );
}
