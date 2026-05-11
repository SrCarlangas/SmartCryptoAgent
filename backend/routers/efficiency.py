"""Endpoints de análisis de eficiencia. RIESGO CERO — solo lectura.

Mide qué tanto se está dejando en la mesa parseando bot.log y agregando con
trade_history. No modifica el comportamiento del bot.

Endpoints:
- GET /api/efficiency/trade-postmortem: por cada SELL, calcula el max precio
  alcanzado en las siguientes N horas → "missed gain".
- GET /api/efficiency/distribution: histograma de PnL por venta para
  detectar clusters pegados al MIN_PROFIT (señal de salida prematura).
- GET /api/efficiency/veto-postmortem: por cada VETO Peak Guard en log,
  cuánto subió/bajó el precio después.
- GET /api/efficiency/summary: vista combinada con métricas clave.
"""
import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Tuple

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from backend.state_bridge import BotState

router = APIRouter(prefix="/api/efficiency", tags=["efficiency"])

LOG_PATH = Path(__file__).resolve().parent.parent.parent / "bot.log"


# ───────────────────────── Schemas ─────────────────────────


class TradePostmortem(BaseModel):
    timestamp: str
    action: str
    sell_price: float
    pnl: Optional[float] = None
    fee: float = 0.0
    lookahead_hours: float
    max_price_after: Optional[float] = None
    max_price_at: Optional[str] = None
    missed_pct: Optional[float] = None  # % entre sell_price y max_price_after
    min_price_after: Optional[float] = None
    drop_pct: Optional[float] = None    # caída desde sell_price (positivo = bajó)
    samples: int = 0


class TradePostmortemResponse(BaseModel):
    items: List[TradePostmortem]
    summary: dict


class RoiBucket(BaseModel):
    label: str
    range_low: float
    range_high: float
    count: int
    total_pnl: float


class DistributionResponse(BaseModel):
    buckets: List[RoiBucket]
    total_trades: int
    total_pnl: float
    pct_below_threshold: float  # % de trades con PnL < $1
    pct_negative: float
    avg_pnl: float
    median_pnl: float


class VetoPostmortem(BaseModel):
    timestamp: str
    veto_type: str  # "Peak Guard" | "ADX 1h" | "Filtro macro" | etc.
    blocked_price: float
    reason: str
    price_after_1h: Optional[float] = None
    price_after_4h: Optional[float] = None
    return_1h_pct: Optional[float] = None
    return_4h_pct: Optional[float] = None
    would_have_been_profitable: Optional[bool] = None  # 1h return >= 0.4%


class VetoPostmortemResponse(BaseModel):
    items: List[VetoPostmortem]
    summary: dict


class EfficiencySummary(BaseModel):
    period_days: int
    total_sells: int
    total_pnl: float
    total_fees: float
    fee_burden_pct: float
    avg_pnl_per_sell: float
    median_pnl_per_sell: float
    pct_micro_wins: float  # < $1
    pct_negative_sells: float
    avg_missed_pct: float = Field(default=0.0)
    sells_with_significant_miss: int = Field(default=0)  # missed > 1%
    veto_count: int = 0
    profitable_vetos_pct: float = 0.0
    recommendation: str = ""


# ───────────────────────── Helpers ─────────────────────────


_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
_PRICE_RE = re.compile(r"P:(\d+(?:\.\d+)?)")
_VETO_RE = re.compile(r"🛡️\s*RISK GUARDIAN VETO\s*\(\d+x\):\s*(.+?)$")
_VETO_PRICE_RE = re.compile(r"P:(\d+(?:\.\d+)?)")


def _parse_log_line_ts(line: str) -> Optional[datetime]:
    m = _TS_RE.match(line)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def _list_log_files() -> List[Path]:
    """Devuelve [bot.log.N, ..., bot.log.1, bot.log] en orden cronológico
    (más viejo primero). RotatingFileHandler rota así: bot.log.1 es el backup
    más reciente, bot.log.5 el más viejo. El archivo actual es bot.log.
    """
    base = LOG_PATH.parent
    files = []
    if not LOG_PATH.exists():
        return files
    # Backups rotados (bot.log.1, bot.log.2, ...) — más altos = más viejos
    backups = sorted(base.glob("bot.log.*"),
                     key=lambda p: int(p.suffix.lstrip(".")) if p.suffix.lstrip(".").isdigit() else 0,
                     reverse=True)
    files.extend(backups)
    files.append(LOG_PATH)
    return files


def _load_log_prices(since: datetime, until: datetime) -> List[Tuple[datetime, float]]:
    """Extrae (timestamp, price) de bot.log y rotados dentro de [since, until].

    No usa break-early porque RotatingFileHandler crea discontinuidades en el
    archivo individual (un mismo bot.log puede tener segmentos pre-restart).
    """
    out: List[Tuple[datetime, float]] = []
    for log_path in _list_log_files():
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    dt = _parse_log_line_ts(line)
                    if dt is None:
                        continue
                    if dt < since or dt > until:
                        continue
                    m = _PRICE_RE.search(line)
                    if m:
                        try:
                            price = float(m.group(1))
                            if price > 1000:
                                out.append((dt, price))
                        except Exception:
                            pass
        except Exception:
            continue
    out.sort(key=lambda x: x[0])
    return out


def _parse_trade_ts(t: dict) -> Optional[datetime]:
    ts = t.get("timestamp", "")
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except Exception:
        try:
            return datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S")
        except Exception:
            return None


def _max_min_in_window(
    prices: List[Tuple[datetime, float]], start: datetime, end: datetime
) -> Tuple[Optional[float], Optional[datetime], Optional[float], int]:
    """Devuelve (max_price, max_at, min_price, n_samples) dentro del rango."""
    in_window = [(t, p) for t, p in prices if start <= t <= end]
    if not in_window:
        return None, None, None, 0
    max_p = max(p for _, p in in_window)
    max_at = next(t for t, p in in_window if p == max_p)
    min_p = min(p for _, p in in_window)
    return max_p, max_at, min_p, len(in_window)


def _price_at(
    prices: List[Tuple[datetime, float]], target: datetime, tolerance_minutes: int = 5
) -> Optional[float]:
    """Encuentra el precio más cercano al timestamp target dentro de tolerancia."""
    best = None
    best_delta = None
    delta_max = timedelta(minutes=tolerance_minutes)
    for t, p in prices:
        d = abs(t - target)
        if d > delta_max:
            continue
        if best_delta is None or d < best_delta:
            best = p
            best_delta = d
    return best


# ───────────────────────── Endpoints ─────────────────────────


@router.get("/trade-postmortem", response_model=TradePostmortemResponse)
def trade_postmortem(
    days: int = Query(7, ge=1, le=90),
    lookahead_hours: float = Query(4.0, ge=0.5, le=72.0),
):
    """Para cada SELL en los últimos N días, busca max precio en las
    siguientes `lookahead_hours` horas y calcula el "missed gain".

    El missed_pct se interpreta como: si hubieras esperado las próximas N
    horas en lugar de vender, cuánto más habrías ganado por unidad."""
    bs = BotState.get()
    estado = bs.snapshot()
    trades = list(estado.get("trade_history", []) or [])

    cutoff = datetime.now() - timedelta(days=days)
    sells = [
        t for t in trades
        if t.get("action") in ("SELL", "PARTIAL_SELL")
        and (_parse_trade_ts(t) or datetime.min) >= cutoff
    ]

    if not sells:
        return TradePostmortemResponse(items=[], summary={
            "period_days": days, "lookahead_hours": lookahead_hours,
            "sells_analyzed": 0,
        })

    # Cargar precios del log con margen
    earliest = min((_parse_trade_ts(t) for t in sells if _parse_trade_ts(t)), default=cutoff)
    latest = max((_parse_trade_ts(t) for t in sells if _parse_trade_ts(t)), default=datetime.now())
    log_prices = _load_log_prices(
        since=earliest - timedelta(minutes=10),
        until=latest + timedelta(hours=lookahead_hours + 1),
    )

    items: List[TradePostmortem] = []
    missed_pcts: List[float] = []
    significant_miss = 0

    for t in sells:
        ts = _parse_trade_ts(t)
        if not ts:
            continue
        sell_price = float(t.get("price", 0) or 0)
        if sell_price <= 0:
            continue
        end = ts + timedelta(hours=lookahead_hours)
        max_p, max_at, min_p, n = _max_min_in_window(log_prices, ts, end)

        missed_pct = None
        drop_pct = None
        if max_p is not None and sell_price > 0:
            missed_pct = (max_p - sell_price) / sell_price * 100
            missed_pcts.append(missed_pct)
            if missed_pct > 1.0:
                significant_miss += 1
        if min_p is not None and sell_price > 0:
            drop_pct = (sell_price - min_p) / sell_price * 100  # positivo = sell evitó pérdida

        items.append(TradePostmortem(
            timestamp=t.get("timestamp", ""),
            action=t.get("action", ""),
            sell_price=sell_price,
            pnl=t.get("pnl"),
            fee=float(t.get("fee", 0) or 0),
            lookahead_hours=lookahead_hours,
            max_price_after=max_p,
            max_price_at=max_at.isoformat() if max_at else None,
            missed_pct=missed_pct,
            min_price_after=min_p,
            drop_pct=drop_pct,
            samples=n,
        ))

    avg_missed = sum(missed_pcts) / len(missed_pcts) if missed_pcts else 0
    median_missed = sorted(missed_pcts)[len(missed_pcts) // 2] if missed_pcts else 0
    max_missed = max(missed_pcts) if missed_pcts else 0

    summary = {
        "period_days": days,
        "lookahead_hours": lookahead_hours,
        "sells_analyzed": len(items),
        "sells_with_data": sum(1 for i in items if i.max_price_after is not None),
        "avg_missed_pct": round(avg_missed, 4),
        "median_missed_pct": round(median_missed, 4),
        "max_missed_pct": round(max_missed, 4),
        "sells_with_significant_miss": significant_miss,  # missed > 1%
    }
    return TradePostmortemResponse(items=items, summary=summary)


@router.get("/distribution", response_model=DistributionResponse)
def distribution(days: int = Query(30, ge=1, le=365)):
    """Histograma de PnL por venta. Detecta clusters cerca de break-even."""
    bs = BotState.get()
    estado = bs.snapshot()
    trades = list(estado.get("trade_history", []) or [])
    cutoff = datetime.now() - timedelta(days=days)

    sells = [
        t for t in trades
        if t.get("action") in ("SELL", "PARTIAL_SELL")
        and t.get("pnl") is not None
        and (_parse_trade_ts(t) or datetime.min) >= cutoff
    ]

    pnls = [float(t.get("pnl", 0) or 0) for t in sells]

    # Buckets de PnL en USDT
    bucket_defs = [
        ("Pérdida", -999.0, 0.0),
        ("$0–$0.5", 0.0, 0.5),
        ("$0.5–$1.0", 0.5, 1.0),
        ("$1.0–$2.0", 1.0, 2.0),
        ("$2.0–$3.0", 2.0, 3.0),
        ("$3.0–$5.0", 3.0, 5.0),
        ("$5.0–$10.0", 5.0, 10.0),
        ("$10.0+", 10.0, 999.0),
    ]
    buckets = []
    for label, lo, hi in bucket_defs:
        bucket_pnls = [p for p in pnls if lo <= p < hi]
        buckets.append(RoiBucket(
            label=label, range_low=lo, range_high=hi,
            count=len(bucket_pnls), total_pnl=round(sum(bucket_pnls), 4),
        ))

    total = len(pnls)
    total_pnl = sum(pnls)
    avg_pnl = total_pnl / total if total else 0
    median_pnl = sorted(pnls)[total // 2] if total else 0
    pct_below_threshold = sum(1 for p in pnls if 0 <= p < 1.0) / total * 100 if total else 0
    pct_negative = sum(1 for p in pnls if p < 0) / total * 100 if total else 0

    return DistributionResponse(
        buckets=buckets,
        total_trades=total,
        total_pnl=round(total_pnl, 4),
        pct_below_threshold=round(pct_below_threshold, 2),
        pct_negative=round(pct_negative, 2),
        avg_pnl=round(avg_pnl, 4),
        median_pnl=round(median_pnl, 4),
    )


@router.get("/veto-postmortem", response_model=VetoPostmortemResponse)
def veto_postmortem(days: int = Query(7, ge=1, le=30)):
    """Por cada VETO Peak Guard / ADX / Macro, mide retorno 1h y 4h después."""
    if not LOG_PATH.exists():
        return VetoPostmortemResponse(items=[], summary={"vetos": 0})

    cutoff = datetime.now() - timedelta(days=days)
    until = datetime.now()
    log_prices = _load_log_prices(cutoff - timedelta(minutes=10), until + timedelta(hours=5))

    vetos: List[Tuple[datetime, str, str, float]] = []  # (ts, type, reason, price)
    try:
        with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                dt = _parse_log_line_ts(line)
                if dt is None or dt < cutoff:
                    continue
                m = _VETO_RE.search(line)
                if not m:
                    continue
                reason = m.group(1).strip()
                if "Peak Guard" in reason:
                    veto_type = "Peak Guard"
                elif "ADX 1h" in reason:
                    veto_type = "ADX bajista"
                elif "Filtro macro" in reason:
                    veto_type = "EMA50 1h"
                elif "Exposicion" in reason or "exposicion" in reason.lower():
                    veto_type = "Exposición"
                elif "Reserva USDT" in reason or "reserva" in reason.lower():
                    veto_type = "Reserva USDT"
                elif "Max posiciones" in reason:
                    veto_type = "Max posiciones"
                elif "DCA" in reason:
                    veto_type = "DCA bloqueado"
                else:
                    veto_type = "Otro"
                pmatch = _VETO_PRICE_RE.search(reason)
                price = float(pmatch.group(1)) if pmatch else 0.0
                if price <= 0:
                    # fallback: intentar precio del context cercano
                    price = _price_at(log_prices, dt, tolerance_minutes=2) or 0.0
                if price > 0:
                    vetos.append((dt, veto_type, reason[:140], price))
    except Exception:
        pass

    items: List[VetoPostmortem] = []
    profitable_count = 0
    for ts, vtype, reason, price in vetos:
        p1h = _price_at(log_prices, ts + timedelta(hours=1), tolerance_minutes=10)
        p4h = _price_at(log_prices, ts + timedelta(hours=4), tolerance_minutes=15)
        ret1 = ((p1h - price) / price * 100) if (p1h and price > 0) else None
        ret4 = ((p4h - price) / price * 100) if (p4h and price > 0) else None
        prof = (ret1 is not None and ret1 >= 0.4)  # 0.4% = MIN_PROFIT_AFTER_FEES
        if prof:
            profitable_count += 1
        items.append(VetoPostmortem(
            timestamp=ts.isoformat(),
            veto_type=vtype, reason=reason, blocked_price=price,
            price_after_1h=p1h, price_after_4h=p4h,
            return_1h_pct=ret1, return_4h_pct=ret4,
            would_have_been_profitable=prof,
        ))

    types = Counter(v[1] for v in vetos)
    pct_profitable = (profitable_count / len(items) * 100) if items else 0
    summary = {
        "period_days": days,
        "total_vetos": len(items),
        "by_type": dict(types),
        "profitable_count": profitable_count,
        "profitable_pct": round(pct_profitable, 2),
    }
    return VetoPostmortemResponse(items=items, summary=summary)


@router.get("/summary", response_model=EfficiencySummary)
def summary(days: int = Query(7, ge=1, le=90)):
    """Vista consolidada: las métricas clave de eficiencia con recomendación."""
    pm = trade_postmortem(days=days, lookahead_hours=4.0)
    dist = distribution(days=days)
    vp = veto_postmortem(days=min(days, 30))

    bs = BotState.get()
    estado = bs.snapshot()
    cutoff = datetime.now() - timedelta(days=days)
    sells = [
        t for t in (estado.get("trade_history") or [])
        if t.get("action") in ("SELL", "PARTIAL_SELL")
        and (_parse_trade_ts(t) or datetime.min) >= cutoff
    ]
    total_pnl = sum(float(t.get("pnl") or 0) for t in sells)
    total_fees = sum(float(t.get("fee") or 0) for t in sells)
    fee_burden = (total_fees / total_pnl * 100) if total_pnl > 0 else 0.0

    avg_missed = pm.summary.get("avg_missed_pct", 0)
    rec = []
    if fee_burden > 18:
        rec.append("Fees consumen >18% del PnL: salidas demasiado tempranas")
    if dist.pct_below_threshold > 12:
        rec.append("Más del 12% de ventas son micro-wins (<$1) — considerar elevar TP base")
    if dist.pct_negative > 5:
        rec.append("Más del 5% de ventas en pérdida — MIN_PROFIT_AFTER_FEES insuficiente")
    if avg_missed > 0.5:
        rec.append(f"Missed gain medio {avg_missed:.2f}% — trailing stop probablemente muy agresivo")
    if vp.summary.get("profitable_pct", 0) > 40:
        rec.append("Más del 40% de vetos hubieran sido rentables — Peak Guard restrictivo")
    if not rec:
        rec.append("Parámetros actuales razonables; sin acciones recomendadas")

    return EfficiencySummary(
        period_days=days,
        total_sells=len(sells),
        total_pnl=round(total_pnl, 4),
        total_fees=round(total_fees, 4),
        fee_burden_pct=round(fee_burden, 2),
        avg_pnl_per_sell=round(dist.avg_pnl, 4),
        median_pnl_per_sell=round(dist.median_pnl, 4),
        pct_micro_wins=round(dist.pct_below_threshold, 2),
        pct_negative_sells=round(dist.pct_negative, 2),
        avg_missed_pct=round(avg_missed, 4),
        sells_with_significant_miss=pm.summary.get("sells_with_significant_miss", 0),
        veto_count=vp.summary.get("total_vetos", 0),
        profitable_vetos_pct=round(vp.summary.get("profitable_pct", 0), 2),
        recommendation=" · ".join(rec),
    )
