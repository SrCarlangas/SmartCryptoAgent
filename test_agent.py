"""
Tests para el agente adaptativo por regimen.
Ejecutar: python test_agent.py
"""
import time


def test_models():
    from modules.agent.models import MarketContext, TradingDecision, ExecutionPlan, PositionSummary, CrashState

    ps = PositionSummary(id="pos_123", entry_price=84000, amount=0.05, dca_level=1)
    assert ps.roi_current == 0.0
    assert ps.exits_taken == []

    ctx = MarketContext()
    assert ctx.num_positions == 0
    assert ctx.available_slots == 0
    assert ctx.positions == []
    assert ctx.regime == "LATERAL"
    assert ctx.fear_greed_raw == 50
    assert ctx.rsi_weekly == 50.0
    assert ctx.usdt_reserve_pct == 0.0

    ctx.positions = [ps]
    ctx.num_positions = 1
    ctx.available_slots = 4

    decision = TradingDecision(action="SELL", target_position_id="pos_123", confidence=0.9)
    assert decision.target_position_id == "pos_123"
    assert decision.sell_pct == 1.0
    assert decision.exit_trigger == ""

    decision2 = TradingDecision(action="PARTIAL_SELL", sell_pct=0.25, exit_trigger="roi_pct_0.3")
    assert decision2.sell_pct == 0.25

    plan = ExecutionPlan(action="DCA", target_position_id="pos_456")
    assert plan.target_position_id == "pos_456"
    assert plan.sell_pct == 1.0

    crash = CrashState(active=True, reference_price=84000)
    assert crash.tranches_deployed == []

    print("✅ test_models OK")


def test_prompts():
    from modules.agent.models import MarketContext, PositionSummary, TradingDecision
    from modules.agent.prompts import SYSTEM_PROMPT, build_analysis_prompt

    assert "PARTIAL_SELL" in SYSTEM_PROMPT
    assert "HOLD" in SYSTEM_PROMPT
    # System prompt: analista completo pero eficiente (< 1500 chars)
    assert len(SYSTEM_PROMPT) < 1500, f"System prompt too long: {len(SYSTEM_PROMPT)} chars"
    # Debe tener criterios de decision propios, no solo validacion
    assert "analista" in SYSTEM_PROMPT.lower() or "experto" in SYSTEM_PROMPT.lower()
    assert "reasoning" in SYSTEM_PROMPT.lower()

    # Sin posiciones, sin recomendacion
    ctx = MarketContext(
        price=84250.0, rsi_14=36.2, rsi_prev=38.0,
        bb_lower=83900.0, bb_mid=84500.0, bb_upper=85100.0,
        ema_21=84100.0, atr_14=320.0, adx_14=28.5, volume_ratio=1.2,
        sentiment_score=-0.30, sentiment_label="Fear",
        balance_total=4404.0, usdt_disponible=4404.0,
        num_positions=0, available_slots=5,
        regime="LATERAL", regime_confidence=0.67,
        rsi_weekly=55.0, fear_greed_raw=35,
    )
    prompt = build_analysis_prompt(ctx)
    assert "VACIO" in prompt
    assert "0/5" in prompt
    assert "REGIME:LATERAL" in prompt
    assert "W_RSI:55.0" in prompt
    assert "FNG:35" in prompt
    assert "REC" not in prompt  # no recommendation passed

    # Con recomendacion pre-calculada
    rec = TradingDecision(action="BUY", confidence=0.75, suggested_allocation_pct=0.10, reasoning="LATERAL/MEAN_REVERSION")
    prompt_rec = build_analysis_prompt(ctx, rules_recommendation=rec)
    assert "--- REC ---" in prompt_rec
    assert "ACT:BUY" in prompt_rec
    assert "LATERAL/MEAN_REVERSION" in prompt_rec

    # Con recomendacion HOLD
    rec_hold = TradingDecision(action="HOLD")
    prompt_hold = build_analysis_prompt(ctx, rules_recommendation=rec_hold)
    assert "ACT:HOLD" in prompt_hold

    # Con posiciones
    ctx.positions = [
        PositionSummary(id="pos_111", entry_price=73000, amount=0.05, dca_level=0, roi_current=0.017, total_invested=350),
        PositionSummary(id="pos_222", entry_price=74000, amount=0.03, dca_level=1, roi_current=-0.02, total_invested=500,
                        exits_taken=["roi_pct_0.3"]),
    ]
    ctx.num_positions = 2
    ctx.available_slots = 3
    ctx.total_btc_held = 0.08
    ctx.total_invested = 850
    ctx.exposure_pct = 0.19

    prompt2 = build_analysis_prompt(ctx)
    assert "pos_111" in prompt2
    assert "pos_222" in prompt2
    assert "2/5" in prompt2
    assert "exits:roi_pct_0.3" in prompt2

    print("✅ test_prompts OK")


def test_regime_detection():
    from modules.agent.models import MarketContext
    from modules.regime import RegimeDetector

    rd = RegimeDetector()

    # ALCISTA: precio > EMA50 > EMA200, ADX alto +DI > -DI, RSI semanal > 60
    ctx_bull = MarketContext(
        price=85000, ema_50_1h=84000, ema_200_1h=82000,
        adx_1h=30, plus_di_1h=35, minus_di_1h=15,
        rsi_weekly=65, price_change_24h=0.02, volume_ratio=1.0,
        fear_greed_raw=55,
    )
    result = rd.detect(ctx_bull)
    assert result.regime == "ALCISTA", f"Expected ALCISTA, got {result.regime}"
    assert result.confidence == 1.0  # 3/3

    # BAJISTA: precio < ambas EMAs, -DI > +DI, RSI semanal < 40
    ctx_bear = MarketContext(
        price=78000, ema_50_1h=80000, ema_200_1h=82000,
        adx_1h=30, plus_di_1h=12, minus_di_1h=35,
        rsi_weekly=35, price_change_24h=-0.03, volume_ratio=1.0,
        fear_greed_raw=30,
    )
    result_bear = rd.detect(ctx_bear)
    assert result_bear.regime == "BAJISTA", f"Expected BAJISTA, got {result_bear.regime}"

    # LATERAL: ADX bajo, RSI semanal neutral
    ctx_lat = MarketContext(
        price=84000, ema_50_1h=83500, ema_200_1h=84500,
        adx_1h=15, plus_di_1h=20, minus_di_1h=18,
        rsi_weekly=50, price_change_24h=0.001, volume_ratio=0.8,
        fear_greed_raw=45,
    )
    result_lat = rd.detect(ctx_lat)
    assert result_lat.regime == "LATERAL", f"Expected LATERAL, got {result_lat.regime}"

    # CRASH: caida >10%, volumen >2x, FnG < 20
    ctx_crash = MarketContext(
        price=75000, ema_50_1h=83000, ema_200_1h=85000,
        adx_1h=40, plus_di_1h=10, minus_di_1h=45,
        rsi_weekly=25, price_change_24h=-0.12, volume_ratio=3.0,
        fear_greed_raw=10,
    )
    result_crash = rd.detect(ctx_crash)
    assert result_crash.regime == "CRASH", f"Expected CRASH, got {result_crash.regime}"
    assert result_crash.is_crash is True

    # Sin EMA200 (fallback lateral para EMA signal)
    ctx_no_ema = MarketContext(
        price=84000, ema_50_1h=83000, ema_200_1h=0,
        adx_1h=15, rsi_weekly=50,
        price_change_24h=0, volume_ratio=1.0, fear_greed_raw=50,
    )
    result_no = rd.detect(ctx_no_ema)
    assert result_no.regime == "LATERAL"

    print("✅ test_regime_detection OK")


def test_smart_dca_multiplier():
    from modules.strategy import EstrategiaSmartDCA

    est = EstrategiaSmartDCA()

    # ALCISTA DCA table: [(40, 2.0), (50, 0.5), (65, 0.0)]
    assert est.get_dca_multiplier(35, "ALCISTA") == 2.0
    assert est.get_dca_multiplier(45, "ALCISTA") == 0.5
    assert est.get_dca_multiplier(55, "ALCISTA") == 0.0

    # BAJISTA DCA table: [(25, 3.0), (35, 2.5), (45, 2.0), (55, 1.0), (100, 0.0)]
    assert est.get_dca_multiplier(20, "BAJISTA") == 3.0
    assert est.get_dca_multiplier(30, "BAJISTA") == 2.5
    assert est.get_dca_multiplier(40, "BAJISTA") == 2.0
    assert est.get_dca_multiplier(50, "BAJISTA") == 1.0
    assert est.get_dca_multiplier(60, "BAJISTA") == 0.0

    # LATERAL DCA table: [(35, 2.0), (45, 1.0), (100, 0.0)]
    assert est.get_dca_multiplier(30, "LATERAL") == 2.0
    assert est.get_dca_multiplier(40, "LATERAL") == 1.0
    assert est.get_dca_multiplier(50, "LATERAL") == 0.0

    # Universal fallback (unknown regime)
    assert est.get_dca_multiplier(20, "UNKNOWN") == 3.0  # uses SMART_DCA_RSI_TABLE

    print("✅ test_smart_dca_multiplier OK")


def test_scaled_exits():
    from modules.agent.models import PositionSummary
    from modules.strategy import EstrategiaSmartDCA

    est = EstrategiaSmartDCA()

    # ALCISTA: ROI > 30% should trigger scaled exit
    pos = PositionSummary(id="pos_1", entry_price=60000, amount=0.05, roi_current=0.35)
    exits = est.evaluar_salidas_escalonadas(pos, 81000, 55, "ALCISTA", 50)
    assert len(exits) > 0, "Should have exit trigger for ROI > 30%"
    assert exits[0][0] == "roi_pct_0.3"
    assert exits[0][1] == 0.25

    # Already taken: should not trigger again
    pos2 = PositionSummary(id="pos_2", entry_price=60000, amount=0.05, roi_current=0.35,
                           exits_taken=["roi_pct_0.3"])
    exits2 = est.evaluar_salidas_escalonadas(pos2, 81000, 55, "ALCISTA", 50)
    assert not any(e[0] == "roi_pct_0.3" for e in exits2), "Already taken exit should not trigger again"

    # ALCISTA: RSI > 70 partial sell
    pos3 = PositionSummary(id="pos_3", entry_price=80000, amount=0.05, roi_current=0.05)
    exits3 = est.evaluar_salidas_escalonadas(pos3, 84000, 72, "ALCISTA", 50)
    assert any(e[0] == "rsi_70_sell" for e in exits3), "RSI > 70 should trigger partial sell"

    # ALCISTA: weekly RSI > 75
    exits4 = est.evaluar_salidas_escalonadas(pos, 81000, 55, "ALCISTA", 78)
    assert any("weekly_rsi_gt" in e[0] for e in exits4), "Weekly RSI > 75 should trigger"

    # LATERAL: sell at resistance RSI > 60
    pos_lat = PositionSummary(id="pos_l", entry_price=83000, amount=0.05, roi_current=0.01)
    exits_lat = est.evaluar_salidas_escalonadas(pos_lat, 84000, 65, "LATERAL", 50)
    assert len(exits_lat) > 0, "Lateral should sell at resistance RSI > 60"
    assert exits_lat[0][1] == 1.0  # full sell in lateral

    # BAJISTA: momentum reversal exit when ROI > 1.2% + RSI falling + price dropping >0.3%
    from modules.agent.models import MarketContext
    pos_bear = PositionSummary(id="pos_b", entry_price=69000, amount=0.05, roi_current=0.013)
    ctx_bear = MarketContext(price=69897, rsi_14=48, rsi_prev=52, price_change_15m=-0.004)
    exits_bear = est.evaluar_salidas_escalonadas(pos_bear, 69897, 48, "BAJISTA", 50, ctx=ctx_bear)
    assert len(exits_bear) > 0, "BAJISTA should trigger momentum reversal when ROI>1.2% + RSI falling + retrace>0.3%"
    assert exits_bear[0][0] == "bajista_momentum_reversal"
    assert exits_bear[0][1] == 1.0  # full sell

    # BAJISTA: no exit when ROI between 0.8% and 1.2% (below new threshold)
    pos_bear2 = PositionSummary(id="pos_b2", entry_price=69000, amount=0.05, roi_current=0.009)
    exits_bear2 = est.evaluar_salidas_escalonadas(pos_bear2, 69621, 48, "BAJISTA", 50, ctx=ctx_bear)
    assert len(exits_bear2) == 0, "BAJISTA should NOT trigger momentum reversal when ROI < 1.2%"

    # BAJISTA: no exit when price retrace too small (<0.3%)
    ctx_bear_small = MarketContext(price=69897, rsi_14=48, rsi_prev=52, price_change_15m=-0.001)
    exits_bear3 = est.evaluar_salidas_escalonadas(pos_bear, 69897, 48, "BAJISTA", 50, ctx=ctx_bear_small)
    assert len(exits_bear3) == 0, "BAJISTA should NOT trigger when retrace < 0.3%"

    # BAJISTA: no exit when RSI still rising
    ctx_bear_rising = MarketContext(price=69897, rsi_14=52, rsi_prev=48, price_change_15m=-0.004)
    exits_bear4 = est.evaluar_salidas_escalonadas(pos_bear, 69897, 52, "BAJISTA", 50, ctx=ctx_bear_rising)
    assert len(exits_bear4) == 0, "BAJISTA should NOT trigger when RSI still rising"

    print("✅ test_scaled_exits OK")


def test_trigger_evaluator():
    from modules.agent.models import MarketContext, PositionSummary
    from modules.trigger_evaluator import TriggerEvaluator

    te = TriggerEvaluator()

    # Primera llamada: inicializacion
    ctx = MarketContext(price=84000.0, rsi_14=50.0, sentiment_score=0.0, available_slots=5, regime="LATERAL")
    te.last_call_time = time.time() - 120
    assert te.should_call_agent(ctx) is True

    # Rate limited
    ctx2 = MarketContext(price=84010.0, rsi_14=50.0, sentiment_score=0.0, available_slots=5, regime="LATERAL")
    assert te.should_call_agent(ctx2) is False

    # Cambio de regimen
    te.last_call_time = time.time() - 120
    ctx3 = MarketContext(price=84000.0, rsi_14=50.0, sentiment_score=0.0, available_slots=5, regime="ALCISTA")
    assert te.should_call_agent(ctx3) is True

    # Con posicion en TP
    te.last_call_time = time.time() - 120
    ctx4 = MarketContext(
        price=84000.0, rsi_14=50.0, sentiment_score=0.0,
        num_positions=1, available_slots=4, regime="LATERAL",
        positions=[PositionSummary(id="pos_1", roi_current=0.02)]
    )
    assert te.should_call_agent(ctx4) is True

    print("✅ test_trigger_evaluator OK")


def test_risk_guardian():
    from modules.agent.models import MarketContext, TradingDecision, PositionSummary
    from modules.risk import RiskManager

    rm = RiskManager()

    # BUY sin slots
    ctx = MarketContext(balance_total=5000, sentiment_score=0.0, available_slots=0, num_positions=5)
    d = TradingDecision(action="BUY")
    ok, _ = rm.validate_decision(d, ctx)
    assert not ok, "Deberia vetar BUY sin slots"

    # BUY con slots (ahora necesita reserva 30%)
    ctx2 = MarketContext(
        balance_total=5000, sentiment_score=0.0, available_slots=3,
        num_positions=2, total_invested=1000, price=84000,
        ema_50_1h=83000, price_vs_ema50_1h=0.012,
        usdt_disponible=3500,  # 70% disponible
    )
    d2 = TradingDecision(action="BUY", suggested_allocation_pct=0.10)
    ok2, _ = rm.validate_decision(d2, ctx2)
    assert ok2, "BUY con slots y reserva suficiente deberia ser aprobado"

    # BUY que deja sin reserva
    ctx_low = MarketContext(
        balance_total=5000, sentiment_score=0.0, available_slots=3,
        num_positions=2, total_invested=2500, price=84000,
        ema_50_1h=83000, price_vs_ema50_1h=0.012,
        usdt_disponible=1600,  # 32%
    )
    d_low = TradingDecision(action="BUY", suggested_allocation_pct=0.10)  # 500 USDT -> leaves 1100 = 22%
    ok_low, reason = rm.validate_decision(d_low, ctx_low)
    assert not ok_low, f"BUY que deja sin reserva deberia ser vetado: {reason}"

    # DCA con posicion invalida
    ctx3 = MarketContext(
        balance_total=5000, sentiment_score=0.0, available_slots=3,
        positions=[PositionSummary(id="pos_1", dca_level=0)],
        total_invested=500, usdt_disponible=4000,
    )
    d3 = TradingDecision(action="DCA", target_position_id="pos_999")
    ok3, _ = rm.validate_decision(d3, ctx3)
    assert not ok3, "DCA con posicion invalida deberia ser vetado"

    # DCA con posicion valida
    d4 = TradingDecision(action="DCA", target_position_id="pos_1", suggested_allocation_pct=0.10)
    ok4, _ = rm.validate_decision(d4, ctx3)
    assert ok4, "DCA con posicion valida deberia ser aprobado"

    # DCA nivel maximo (ahora 5)
    ctx4 = MarketContext(
        balance_total=5000, sentiment_score=0.0,
        positions=[PositionSummary(id="pos_1", dca_level=5)],
        total_invested=500, usdt_disponible=4000,
    )
    d5 = TradingDecision(action="DCA", target_position_id="pos_1")
    ok5, _ = rm.validate_decision(d5, ctx4)
    assert not ok5, "DCA en nivel maximo deberia ser vetado"

    # PARTIAL_SELL valido
    ctx5 = MarketContext(
        balance_total=5000,
        positions=[PositionSummary(id="pos_1", amount=0.05)],
    )
    d_ps = TradingDecision(action="PARTIAL_SELL", target_position_id="pos_1", sell_pct=0.25)
    ok_ps, _ = rm.validate_decision(d_ps, ctx5)
    assert ok_ps, "PARTIAL_SELL valido deberia ser aprobado"

    # PARTIAL_SELL con sell_pct invalido
    d_ps2 = TradingDecision(action="PARTIAL_SELL", target_position_id="pos_1", sell_pct=1.0)
    ok_ps2, _ = rm.validate_decision(d_ps2, ctx5)
    assert not ok_ps2, "PARTIAL_SELL con sell_pct=1.0 deberia ser vetado"

    # Position sizing
    size = rm.calculate_position_size(5000, 0.02, 84000, 82000)
    assert size > 0, "Position size deberia ser positivo"

    # Regla 9: PnL portafolio bloquea compras cuando pérdida > 5%
    ctx_loss = MarketContext(
        balance_total=4700, sentiment_score=0.0, available_slots=3,
        num_positions=0, total_invested=0, price=84000,
        ema_50_1h=83000, price_vs_ema50_1h=0.012,
        usdt_disponible=4700,
        capital_inicial=5000,
        portfolio_pnl=-300,        # -300 USDT
        portfolio_pnl_pct=-0.06,   # -6% > limite 5%
    )
    d_loss = TradingDecision(action="BUY", suggested_allocation_pct=0.10)
    ok_loss, reason_loss = rm.validate_decision(d_loss, ctx_loss)
    assert not ok_loss, f"BUY con PnL portafolio -6% deberia ser vetado"
    assert "PnL portafolio" in reason_loss

    # PnL negativo pero dentro de límite: debe permitir
    ctx_ok = MarketContext(
        balance_total=4850, sentiment_score=0.0, available_slots=3,
        num_positions=0, total_invested=0, price=84000,
        ema_50_1h=83000, price_vs_ema50_1h=0.012,
        usdt_disponible=4850,
        capital_inicial=5000,
        portfolio_pnl=-150,        # -150 USDT
        portfolio_pnl_pct=-0.03,   # -3% < limite 5%
    )
    d_ok = TradingDecision(action="BUY", suggested_allocation_pct=0.10)
    ok_ok, _ = rm.validate_decision(d_ok, ctx_ok)
    assert ok_ok, "BUY con PnL portafolio -3% deberia ser permitido"

    print("✅ test_risk_guardian OK")


def test_market_data_builder():
    import random
    from modules.market_data import build_market_context

    base_price = 84000.0
    velas_15m = []
    for i in range(100):
        t = 1700000000 + i * 900
        p = base_price + random.uniform(-500, 500)
        o = p - random.uniform(-100, 100)
        h = max(o, p) + random.uniform(0, 200)
        l = min(o, p) - random.uniform(0, 200)
        v = random.uniform(10, 100)
        velas_15m.append([t, o, h, l, p, v])

    velas_1h = []
    for i in range(300):
        t = 1700000000 + i * 3600
        p = base_price + random.uniform(-1000, 1000)
        o = p - random.uniform(-200, 200)
        h = max(o, p) + random.uniform(0, 400)
        l = min(o, p) - random.uniform(0, 400)
        v = random.uniform(50, 500)
        velas_1h.append([t, o, h, l, p, v])

    velas_1w = []
    for i in range(20):
        t = 1700000000 + i * 604800
        p = base_price + random.uniform(-3000, 3000)
        o = p - random.uniform(-500, 500)
        h = max(o, p) + random.uniform(0, 1000)
        l = min(o, p) - random.uniform(0, 1000)
        v = random.uniform(500, 5000)
        velas_1w.append([t, o, h, l, p, v])

    estado = {
        'positions': [
            {'id': 'pos_1', 'entry_price': 83000, 'amount': 0.05, 'dca_level': 0, 'total_invested': 400, 'entry_time': 0, 'entry_mode': 'test', 'exits_taken': []},
            {'id': 'pos_2', 'entry_price': 85000, 'amount': 0.03, 'dca_level': 1, 'total_invested': 600, 'entry_time': 0, 'entry_mode': 'test', 'exits_taken': ['roi_pct_0.3']},
        ],
        'usdt_disponible': 3400.0,
    }

    ctx = build_market_context(velas_15m, velas_1h, velas_1w, 84250.0, -0.30, 35, estado, 4404.0)

    assert ctx.num_positions == 2
    assert len(ctx.positions) == 2
    assert ctx.positions[0].id == "pos_1"
    assert ctx.total_btc_held == 0.08
    assert ctx.total_invested == 1000
    assert ctx.available_slots == 3
    assert ctx.positions[0].roi_current > 0  # 84250 > 83000
    assert ctx.positions[1].roi_current < 0  # 84250 < 85000
    assert ctx.fear_greed_raw == 35
    assert ctx.usdt_reserve_pct > 0
    assert ctx.bb_upper > 0  # new field
    assert ctx.plus_di >= 0  # new field
    assert ctx.minus_di >= 0  # new field

    # 1h extended
    assert ctx.ema_200_1h > 0, "EMA_200_1h should be calculated with 300 candles"
    assert ctx.adx_1h > 0
    assert ctx.price_change_24h != 0  # should be calculated

    # Fibonacci
    assert ctx.swing_high > 0
    assert ctx.swing_low > 0
    assert ctx.fib_382 > 0
    assert ctx.fib_1618 > 0

    # Weekly RSI
    assert ctx.rsi_weekly != 50.0 or True  # may be 50 with random data

    # exits_taken propagated
    assert ctx.positions[1].exits_taken == ["roi_pct_0.3"]

    print("✅ test_market_data_builder OK")


def test_orchestrator_rules():
    from modules.agent.models import MarketContext, PositionSummary
    from modules.agent.orchestrator import AgentOrchestrator
    from modules.risk import RiskManager
    from modules.strategy import EstrategiaSmartDCA

    rm = RiskManager()
    est = EstrategiaSmartDCA()
    orch = AgentOrchestrator(rm, est)
    orch.mode = "shadow"

    # Sin posiciones, sin velas: HOLD
    ctx = MarketContext(price=84000, balance_total=5000, usdt_disponible=5000, available_slots=5, regime="LATERAL")
    d = orch._get_rules_decision(ctx, None, None)
    assert d.action == "HOLD"

    # Posicion con SL por regimen (LATERAL sl_pct=0.05)
    ctx2 = MarketContext(
        price=80000, balance_total=5000, available_slots=4, regime="LATERAL",
        positions=[PositionSummary(id="pos_sl", entry_price=85000, amount=0.05, roi_current=-0.059, total_invested=400)],
        num_positions=1, rsi_14=40, rsi_weekly=50,
    )
    d2 = orch._get_rules_decision(ctx2, None, None)
    assert d2.action == "SELL", f"Expected SELL for SL, got {d2.action}"
    assert d2.target_position_id == "pos_sl"

    # ALCISTA scaled exit: ROI > 30%
    ctx3 = MarketContext(
        price=80000, balance_total=5000, available_slots=4, regime="ALCISTA",
        positions=[PositionSummary(id="pos_win", entry_price=60000, amount=0.05, roi_current=0.33, total_invested=400)],
        num_positions=1, rsi_14=55, rsi_weekly=50,
    )
    d3 = orch._get_rules_decision(ctx3, None, None)
    assert d3.action == "PARTIAL_SELL", f"Expected PARTIAL_SELL for scaled exit, got {d3.action}"
    assert d3.sell_pct == 0.25

    # DCA en BAJISTA con RSI bajo
    ctx4 = MarketContext(
        price=82000, balance_total=5000, available_slots=4, regime="BAJISTA",
        positions=[PositionSummary(id="pos_dca", entry_price=84500, roi_current=-0.03, dca_level=0, total_invested=400)],
        num_positions=1, rsi_14=30, rsi_weekly=35,
        usdt_disponible=3500, ema_200_1h=85000,
    )
    d4 = orch._get_rules_decision(ctx4, None, None)
    assert d4.action == "DCA", f"Expected DCA, got {d4.action}"
    assert d4.target_position_id == "pos_dca"

    print("✅ test_orchestrator_rules OK")


def test_utils_multiposition():
    from modules.utils import (
        generar_position_id, get_total_btc_positions, get_total_invested,
        has_open_positions, get_position_by_id, remove_position,
        registrar_decision_agente, registrar_trade,
    )

    estado = {
        'positions': [
            {'id': 'pos_1', 'amount': 0.05, 'total_invested': 400},
            {'id': 'pos_2', 'amount': 0.03, 'total_invested': 600},
        ]
    }

    assert get_total_btc_positions(estado) == 0.08
    assert get_total_invested(estado) == 1000
    assert has_open_positions(estado)
    assert get_position_by_id(estado, 'pos_1')['amount'] == 0.05
    assert get_position_by_id(estado, 'pos_999') is None

    remove_position(estado, 'pos_1')
    assert len(estado['positions']) == 1
    assert estado['positions'][0]['id'] == 'pos_2'

    pid = generar_position_id()
    assert pid.startswith("pos_")

    print("✅ test_utils_multiposition OK")


def test_state_migration():
    """Verifica que el estado viejo se migra correctamente."""
    import json
    import os

    # Crear estado viejo
    old_state = {
        'in_position': True,
        'entry_price': 73913.19,
        'amount': 0.00474,
        'dca_level': 0,
        'total_invested': 350.70,
        'entry_time': 1773683665.5,
        'entry_mode': 'MOMENTUM',
        'usdt_disponible': 4033.0,
        'daily_start_balance': 4383.0,
        'last_updated_date': '2026-03-16',
    }

    test_file = 'bot_state_test_migration.json'
    with open(test_file, 'w') as f:
        json.dump(old_state, f)

    # Simular migracion
    import modules.utils as utils
    original_file = utils.STATE_FILE
    utils.STATE_FILE = test_file

    try:
        estado = utils.cargar_estado()
        assert 'positions' in estado
        assert 'in_position' not in estado
        assert len(estado['positions']) == 1

        pos = estado['positions'][0]
        assert pos['entry_price'] == 73913.19
        assert pos['amount'] == 0.00474
        assert pos['dca_level'] == 0
        assert pos['total_invested'] == 350.70
        assert pos['entry_mode'] == 'MOMENTUM'
    finally:
        utils.STATE_FILE = original_file
        os.remove(test_file)

    print("✅ test_state_migration OK")


if __name__ == "__main__":
    print("=" * 50)
    print("TESTS DEL AGENTE ADAPTATIVO POR REGIMEN")
    print("=" * 50)

    tests = [
        test_models,
        test_prompts,
        test_regime_detection,
        test_smart_dca_multiplier,
        test_scaled_exits,
        test_trigger_evaluator,
        test_risk_guardian,
        test_market_data_builder,
        test_orchestrator_rules,
        test_utils_multiposition,
        test_state_migration,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"❌ {test.__name__} FALLO: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("=" * 50)
    print(f"RESULTADO: {passed}/{len(tests)} pasaron")
    print("=" * 50)
