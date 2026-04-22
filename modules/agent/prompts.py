from modules.agent.models import MarketContext, TradingDecision
from config import MAX_DCA_LEVELS


SYSTEM_PROMPT = """Analista experto trading BTC/USDT. TU tomas la decision final.

RECIBES: indicadores tecnicos, regimen, posiciones, PnL_PORT (real acumulado), decisiones previas, y RECOMENDACION de reglas (solo sugerencia).

CRITERIOS POR REGIMEN:
- BUY ALCISTA: comprar en pullback moderado (RSI 40-55, precio cerca EMA21 o zona fib_382-500). En ALCISTA el RSI rara vez baja de 40 — NO esperar sobreventa. Si REC=BUY y régimen=ALCISTA: CONFIRMAR salvo señal clara de techo (pico reciente, RSI>65, momentum negativo).
- BUY LATERAL/BAJISTA: sobreventa confirmada (RSI<40+precio cerca soporte/BB_inf). PnL_PORT<-2%→mas selectivo.
- SELL: LATERAL/BAJISTA ROI>=1.0%+agotamiento (RSI>55, momentum cae). ALCISTA: trailing activo desde 1.0% ROI — vender SOLO si precio cayo >=0.5% desde pico (min 0.7% ROI). Si momentum positivo, HOLD. PnL_PORT negativo→asegurar ganancias.
- DCA: drawdown>2%+RSI<40. HOLD: sin señal clara. PARTIAL_SELL: ROI>2% en rally fuerte.

REGLAS:
1. Fees~0.2%. NO vender ROI<0.4%.
2. BAJISTA: rallies cortos, tomar ganancias ROI 1.0-1.4%.
3. ALCISTA: trailing stop dinamico. Si precio sigue subiendo→HOLD. Si cae desde pico→SELL (min 1% ROI).
4. Consistencia con decisiones previas.
5. Puedes ignorar recomendacion de reglas si tu analisis lo justifica.

JSON: action, confidence(0-1), risk. Solo 3 campos."""


# Schema para forzar respuesta JSON completa en Gemini 2.0 Flash
# Solo 3 campos (reasoning causa truncamiento en 2.0 Flash)
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": ["BUY", "SELL", "HOLD", "DCA", "PARTIAL_SELL"],
        },
        "confidence": {"type": "number"},
        "risk": {
            "type": "string",
            "enum": ["low", "medium", "high"],
        },
    },
    "required": ["action", "confidence", "risk"],
}


def build_analysis_prompt(ctx: MarketContext, rules_recommendation: TradingDecision = None) -> str:
    """Construye el prompt comprimido con datos de mercado + recomendacion pre-calculada."""
    rsi_dir = "^" if ctx.rsi_14 > ctx.rsi_prev else "v"
    ema21_rel = ">" if ctx.price > ctx.ema_21 else "<"

    # Posiciones comprimidas
    all_positions = ctx.positions  # incluye frozen
    active_positions = [p for p in all_positions if not getattr(p, 'is_frozen', False)]
    dca_available = any(p.dca_level < MAX_DCA_LEVELS for p in active_positions)

    if all_positions:
        max_slots = ctx.num_positions + ctx.available_slots
        pos_lines = f"POS({ctx.num_positions}/{max_slots}):\n"
        for p in all_positions:
            exits_str = f"|exits:{','.join(p.exits_taken)}" if p.exits_taken else ""
            frozen_str = "|FROZEN" if getattr(p, 'is_frozen', False) else ""
            dca_str = f"DCA:{p.dca_level}(MAX)" if p.dca_level >= MAX_DCA_LEVELS else f"DCA:{p.dca_level}"
            pos_lines += (
                f" [{p.id}]E:{p.entry_price:.0f}|{p.amount:.5f}BTC"
                f"|{dca_str}|ROI:{p.roi_current*100:+.2f}%"
                f"|${p.total_invested:.0f}|{p.entry_mode[:12]}{frozen_str}{exits_str}\n"
            )
        pos_lines += (
            f"TOT:{ctx.total_btc_held:.5f}BTC|${ctx.total_invested:.0f}"
            f"|EXP:{ctx.exposure_pct*100:.1f}%|SLOTS:{ctx.available_slots}"
        )
        # Restricciones de accion según estado
        if not dca_available:
            pos_lines += "\n⚠️ DCA no disponible: todas las posiciones en nivel maximo"
    else:
        pos_lines = (
            f"POS(0/{ctx.available_slots}):VACIO"
            f"|ult:{ctx.last_trade_result or 'N/A'}"
            f"|cd:{'Si' if ctx.cooldown_active else 'No'}"
            f"\n⚠️ Sin posiciones: SELL/DCA/PARTIAL_SELL no aplicables. Usa BUY o HOLD."
        )

    # EMA200 info
    ema200_str = ""
    if ctx.ema_200_1h > 0:
        ema200_str = f"|EMA200:{ctx.ema_200_1h:.0f}|vsP200:{ctx.price_vs_ema200_1h*100:+.2f}%"

    # ADX 1h con DI
    adx_1h_str = ""
    if ctx.adx_1h > 0:
        adx_1h_str = f"|ADX_1h:{ctx.adx_1h:.0f}|+DI:{ctx.plus_di_1h:.0f}|-DI:{ctx.minus_di_1h:.0f}"

    # Fibonacci
    fib_str = ""
    if ctx.fib_382 > 0:
        fib_str = f"\nFIB:0.382={ctx.fib_382:.0f}|0.5={ctx.fib_500:.0f}|0.618={ctx.fib_618:.0f}|1.618={ctx.fib_1618:.0f}|SH:{ctx.swing_high:.0f}|SL:{ctx.swing_low:.0f}"

    # Recomendacion pre-calculada
    rec_str = ""
    if rules_recommendation and rules_recommendation.action != "HOLD":
        rec_str = (
            f"\n--- REC ---\n"
            f"ACT:{rules_recommendation.action}"
            f"|POS:{rules_recommendation.target_position_id}"
            f"|CONF:{rules_recommendation.confidence:.2f}"
            f"|ALLOC:{rules_recommendation.suggested_allocation_pct:.2f}"
            f"|SELL%:{rules_recommendation.sell_pct:.2f}"
            f"|EXIT:{rules_recommendation.exit_trigger}"
            f"|RAZ:{rules_recommendation.reasoning}"
        )
    elif rules_recommendation:
        rec_str = "\n--- REC ---\nACT:HOLD|Sin señales"

    return (
        f"REGIME:{ctx.regime}({ctx.regime_confidence:.0%})\n"
        f"P:${ctx.price:.2f} d15m:{ctx.price_change_15m*100:+.3f}% d1h:{ctx.price_change_1h*100:+.3f}% d24h:{ctx.price_change_24h*100:+.2f}%\n"
        f"15m|RSI:{ctx.rsi_14:.1f}({rsi_dir})|BB_L:{ctx.bb_lower:.0f}|BB_M:{ctx.bb_mid:.0f}|BB_U:{ctx.bb_upper:.0f}"
        f"|EMA21:{ctx.ema_21:.0f}(P{ema21_rel})|ATR:{ctx.atr_14:.0f}"
        f"|ADX:{ctx.adx_14:.0f}|+DI:{ctx.plus_di:.0f}|-DI:{ctx.minus_di:.0f}"
        f"|Vol:{ctx.volume_ratio:.1f}x|Mom:{ctx.momentum*100:.3f}%\n"
        f"1h|EMA50:{ctx.ema_50_1h:.0f}|vsP:{ctx.price_vs_ema50_1h*100:+.2f}%{ema200_str}{adx_1h_str}\n"
        f"W_RSI:{ctx.rsi_weekly:.1f}{fib_str}\n"
        f"SUP:{ctx.support_price:.0f}|RES:{ctx.resistance_price:.0f}\n"
        f"{pos_lines}\n"
        f"CAP:${ctx.balance_total:.0f}|USDT:${ctx.usdt_disponible:.0f}|RES%:{ctx.usdt_reserve_pct*100:.0f}%"
        f"|SLOTS:{ctx.available_slots}|PnL_PORT:{ctx.portfolio_pnl:+.0f}({ctx.portfolio_pnl_pct*100:+.1f}%)\n"
        f"{ctx.recent_trades_summary}\n"
        f"{ctx.recent_decisions_summary}"
        f"{rec_str}"
    )
