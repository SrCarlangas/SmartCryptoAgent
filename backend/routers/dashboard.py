"""Endpoints readonly para el dashboard."""
from pathlib import Path
from typing import List

from fastapi import APIRouter, HTTPException, Query

from backend.schemas import (
    AgentDecisionOut,
    DailyPnL,
    DailyPnLResponse,
    DashboardSnapshot,
    HealthResponse,
    LogTail,
    PositionOut,
    TradeOut,
)
from backend.state_bridge import BotState
from backend.ws_manager import ws_manager

router = APIRouter(prefix="/api", tags=["dashboard"])

LOG_PATH = Path(__file__).resolve().parent.parent.parent / "bot.log"


def _build_positions(estado: dict, price: float) -> List[PositionOut]:
    out = []
    for p in estado.get("positions", []) or []:
        entry = float(p.get("entry_price", 0) or 0)
        amount = float(p.get("amount", 0) or 0)
        roi = (price - entry) / entry if entry > 0 else 0.0
        out.append(
            PositionOut(
                id=p.get("id", ""),
                entry_price=entry,
                amount=amount,
                dca_level=int(p.get("dca_level", 0) or 0),
                total_invested=float(p.get("total_invested", 0) or 0),
                entry_time=float(p.get("entry_time", 0) or 0),
                entry_mode=p.get("entry_mode", "") or "",
                is_frozen=bool(p.get("is_frozen", False)),
                peak_price=float(p.get("peak_price", 0) or 0),
                roi_current=roi,
                current_value_usdt=amount * price,
            )
        )
    return out


def _build_trades(estado: dict, limit: int = 50) -> List[TradeOut]:
    history = list(estado.get("trade_history", []) or [])
    history = history[-limit:]
    out = []
    for t in history:
        out.append(
            TradeOut(
                timestamp=str(t.get("timestamp", "")),
                action=t.get("action", ""),
                price=float(t.get("price", 0) or 0),
                amount=float(t.get("amount", 0) or 0),
                fee=float(t.get("fee", 0) or 0),
                pnl=t.get("pnl"),
            )
        )
    return out


def _build_decisions(estado: dict, limit: int = 20) -> List[AgentDecisionOut]:
    decisions = list(estado.get("agent_decisions", []) or [])
    decisions = decisions[-limit:]
    out = []
    for d in decisions:
        out.append(
            AgentDecisionOut(
                timestamp=str(d.get("timestamp", "")),
                source=d.get("source", ""),
                action=d.get("action", ""),
                confidence=float(d.get("confidence", 0) or 0),
                reasoning=d.get("reasoning", "") or "",
            )
        )
    return out


@router.get("/health", response_model=HealthResponse)
def health():
    if not BotState.is_initialized():
        return HealthResponse(
            status="starting",
            uptime_s=0,
            bot_alive=False,
            ws_connections=0,
        )
    bs = BotState.get()
    return HealthResponse(
        status="ok",
        uptime_s=bs.uptime_seconds(),
        bot_alive=True,
        ws_connections=ws_manager.num_connections(),
    )


@router.get("/dashboard", response_model=DashboardSnapshot)
def dashboard():
    if not BotState.is_initialized():
        raise HTTPException(503, "Bot still starting up")
    bs = BotState.get()
    estado = bs.snapshot()
    market = bs.get_market_snapshot()

    price = float(market.get("price", 0) or 0)
    positions = _build_positions(estado, price)
    btc_held = sum(p.amount for p in positions)
    capital_inicial = float(estado.get("capital_inicial", 0) or 0)
    usdt_disponible = float(estado.get("usdt_disponible", 0) or 0)
    balance_total = float(market.get("balance_total", 0) or 0)
    if balance_total <= 0:
        balance_total = usdt_disponible + btc_held * price
    portfolio_pnl = balance_total - capital_inicial if capital_inicial > 0 else 0.0
    portfolio_pnl_pct = (
        portfolio_pnl / capital_inicial if capital_inicial > 0 else 0.0
    )
    total_invested = sum(p.total_invested for p in positions)
    exposure_pct = (
        total_invested / balance_total if balance_total > 0 else 0.0
    )

    return DashboardSnapshot(
        mode=bs.get_mode(),
        active_instruction_id=bs.get_active_instruction_id(),
        price=price,
        regime=market.get("regime", "LATERAL"),
        regime_confidence=float(market.get("regime_confidence", 0) or 0),
        balance_total=balance_total,
        usdt_disponible=usdt_disponible,
        btc_held=btc_held,
        capital_inicial=capital_inicial,
        portfolio_pnl=portfolio_pnl,
        portfolio_pnl_pct=portfolio_pnl_pct,
        total_pnl=float(estado.get("total_pnl", 0) or 0),
        total_fees=float(estado.get("total_fees", 0) or 0),
        total_trades=int(estado.get("total_trades", 0) or 0),
        daily_start_balance=float(estado.get("daily_start_balance", 0) or 0),
        num_positions=len(positions),
        available_slots=int(market.get("available_slots", 0) or 0),
        exposure_pct=exposure_pct,
        rsi_14=float(market.get("rsi_14", 50) or 50),
        rsi_weekly=float(market.get("rsi_weekly", 50) or 50),
        cooldown_active=bool(market.get("cooldown_active", False)),
        positions=positions,
        recent_trades=_build_trades(estado, 50),
        recent_decisions=_build_decisions(estado, 20),
        uptime_s=bs.uptime_seconds(),
    )


@router.get("/positions", response_model=List[PositionOut])
def positions():
    bs = BotState.get()
    estado = bs.snapshot()
    market = bs.get_market_snapshot()
    price = float(market.get("price", 0) or 0)
    return _build_positions(estado, price)


@router.get("/trades", response_model=List[TradeOut])
def trades(limit: int = Query(50, ge=1, le=500)):
    bs = BotState.get()
    return _build_trades(bs.snapshot(), limit)


@router.get("/decisions", response_model=List[AgentDecisionOut])
def decisions(limit: int = Query(20, ge=1, le=200)):
    bs = BotState.get()
    return _build_decisions(bs.snapshot(), limit)


@router.get("/pnl-daily", response_model=DailyPnLResponse)
def pnl_daily(days: int = Query(30, ge=1, le=365)):
    """Agrega trade_history por día. Devuelve PnL realizado, fees, conteo por
    tipo, y % sobre el balance estimado al inicio del día."""
    from collections import defaultdict
    from datetime import datetime
    bs = BotState.get()
    estado = bs.snapshot()
    capital_inicial = float(estado.get("capital_inicial", 0) or 0)
    trades = list(estado.get("trade_history", []) or [])

    # Sort cronológicamente
    def parse_ts(t):
        try:
            return datetime.fromisoformat(t.get("timestamp", ""))
        except Exception:
            return datetime.min
    trades.sort(key=parse_ts)

    # Agrupar por día
    by_day = defaultdict(lambda: {"realized": 0.0, "fees": 0.0, "buys": 0,
                                   "sells": 0, "partials": 0, "dcas": 0})
    cum_pnl = 0.0
    day_starting = {}
    for t in trades:
        ts = t.get("timestamp", "")
        if not ts:
            continue
        day = ts[:10]  # YYYY-MM-DD
        if day not in day_starting:
            day_starting[day] = capital_inicial + cum_pnl
        d = by_day[day]
        action = t.get("action", "")
        pnl = t.get("pnl")
        fee = float(t.get("fee") or 0)
        d["fees"] += fee
        if action == "BUY":
            d["buys"] += 1
        elif action == "DCA":
            d["dcas"] += 1
        elif action == "PARTIAL_SELL":
            d["partials"] += 1
        elif action == "SELL":
            d["sells"] += 1
        if isinstance(pnl, (int, float)):
            d["realized"] += float(pnl)
            cum_pnl += float(pnl)

    # Generar lista
    sorted_days = sorted(by_day.keys())
    sorted_days = sorted_days[-days:]
    out_days = []
    for day in sorted_days:
        agg = by_day[day]
        starting = day_starting.get(day, capital_inicial)
        n_trades = agg["buys"] + agg["sells"] + agg["partials"] + agg["dcas"]
        out_days.append(
            DailyPnL(
                date=day,
                realized_pnl=round(agg["realized"], 4),
                fees=round(agg["fees"], 4),
                net_pnl=round(agg["realized"], 4),
                trades=n_trades,
                buys=agg["buys"],
                sells=agg["sells"],
                partial_sells=agg["partials"],
                dcas=agg["dcas"],
                starting_balance=round(starting, 2),
                pct_of_start=round(agg["realized"] / starting * 100, 4) if starting > 0 else 0.0,
            )
        )

    # Resumen
    total_pnl = sum(d.realized_pnl for d in out_days)
    total_fees = sum(d.fees for d in out_days)
    total_trades = sum(d.trades for d in out_days)
    positive_days = sum(1 for d in out_days if d.realized_pnl > 0)
    negative_days = sum(1 for d in out_days if d.realized_pnl < 0)
    flat_days = sum(1 for d in out_days if d.realized_pnl == 0)
    avg_pct = sum(d.pct_of_start for d in out_days) / len(out_days) if out_days else 0
    best = max((d.realized_pnl for d in out_days), default=0)
    worst = min((d.realized_pnl for d in out_days), default=0)

    summary = {
        "total_realized_pnl": round(total_pnl, 4),
        "total_fees": round(total_fees, 4),
        "total_trades": total_trades,
        "days_included": len(out_days),
        "positive_days": positive_days,
        "negative_days": negative_days,
        "flat_days": flat_days,
        "avg_daily_pct": round(avg_pct, 4),
        "best_day_pnl": round(best, 4),
        "worst_day_pnl": round(worst, 4),
    }
    return DailyPnLResponse(days=out_days, summary=summary)


@router.get("/logs", response_model=LogTail)
def logs(lines: int = Query(200, ge=1, le=2000)):
    if not LOG_PATH.exists():
        return LogTail(lines=[], total=0)
    with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
        all_lines = f.readlines()
    tail = all_lines[-lines:]
    return LogTail(
        lines=[ln.rstrip("\n") for ln in tail],
        total=len(all_lines),
    )
