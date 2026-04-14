import pandas as pd
from ta.momentum import RSIIndicator
from ta.volatility import BollingerBands, AverageTrueRange
from ta.trend import EMAIndicator, ADXIndicator
from modules.agent.models import MarketContext, PositionSummary
from modules.logger import logger
from config import MAX_CONCURRENT_POSITIONS, REGIME_PARAMS


def build_market_context(
    velas_15m, velas_1h, velas_1w,
    precio, sentiment_score, fear_greed_raw,
    estado, balance_total
) -> MarketContext:
    """Empaqueta datos crudos de Binance + indicadores en MarketContext."""
    ctx = MarketContext()
    ctx.price = precio
    ctx.sentiment_score = sentiment_score
    ctx.fear_greed_raw = fear_greed_raw
    ctx.balance_total = balance_total
    ctx.usdt_disponible = estado.get('usdt_disponible', 0.0)
    ctx.usdt_reserve_pct = ctx.usdt_disponible / ctx.balance_total if ctx.balance_total > 0 else 1.0

    # Sentiment label
    if sentiment_score < -0.6:
        ctx.sentiment_label = "Extreme Fear"
    elif sentiment_score < -0.2:
        ctx.sentiment_label = "Fear"
    elif sentiment_score < 0.2:
        ctx.sentiment_label = "Neutral"
    elif sentiment_score < 0.6:
        ctx.sentiment_label = "Greed"
    else:
        ctx.sentiment_label = "Extreme Greed"

    # Multi-position state (excluir posiciones congeladas del motor de decisiones)
    positions = estado.get('positions', [])
    ctx.positions = []
    all_btc = 0.0
    for p in positions:
        ps = PositionSummary(
            id=p.get('id', ''),
            entry_price=p.get('entry_price', 0.0),
            amount=p.get('amount', 0.0),
            dca_level=p.get('dca_level', 0),
            total_invested=p.get('total_invested', 0.0),
            entry_time=p.get('entry_time', 0.0),
            entry_mode=p.get('entry_mode', ''),
            exits_taken=p.get('exits_taken', []),
            peak_price=p.get('peak_price', 0.0),
        )
        if ps.entry_price > 0:
            ps.roi_current = (precio - ps.entry_price) / ps.entry_price
        ps.is_frozen = p.get('is_frozen', False)
        all_btc += ps.amount
        ctx.positions.append(ps)  # incluye frozen; is_frozen marca las que solo pueden venderse

    # num_positions y total_invested excluyen frozen para no distorsionar limites de riesgo
    active_positions = [p for p in ctx.positions if not p.is_frozen]
    ctx.num_positions = len(active_positions)
    ctx.total_btc_held = all_btc
    ctx.total_invested = sum(p.total_invested for p in active_positions)
    ctx.available_slots = MAX_CONCURRENT_POSITIONS - ctx.num_positions
    ctx.exposure_pct = ctx.total_invested / ctx.balance_total if ctx.balance_total > 0 else 0

    # ── 15m indicators ──
    if velas_15m and len(velas_15m) >= 50:
        df = pd.DataFrame(velas_15m, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

        bollinger = BollingerBands(close=df['close'], window=20, window_dev=2.0)
        df['BB_Lower'] = bollinger.bollinger_lband()
        df['BB_Mid'] = bollinger.bollinger_mavg()
        df['BB_Upper'] = bollinger.bollinger_hband()
        df['RSI_14'] = RSIIndicator(close=df['close'], window=14).rsi()
        df['EMA_21'] = EMAIndicator(close=df['close'], window=21).ema_indicator()
        df['ATR'] = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14).average_true_range()

        adx_15m = ADXIndicator(high=df['high'], low=df['low'], close=df['close'], window=14)
        df['ADX'] = adx_15m.adx()
        df['Plus_DI'] = adx_15m.adx_pos()
        df['Minus_DI'] = adx_15m.adx_neg()

        df['Vol_SMA_20'] = df['volume'].rolling(window=20).mean()

        v = df.iloc[-2]
        v_ant = df.iloc[-3]

        if not pd.isna(v['RSI_14']):
            ctx.rsi_14 = float(v['RSI_14'])
            ctx.rsi_prev = float(v_ant['RSI_14']) if not pd.isna(v_ant['RSI_14']) else ctx.rsi_14
        if not pd.isna(v['BB_Lower']):
            ctx.bb_lower = float(v['BB_Lower'])
            ctx.bb_mid = float(v['BB_Mid'])
            ctx.bb_upper = float(v['BB_Upper'])
        if not pd.isna(v['EMA_21']):
            ctx.ema_21 = float(v['EMA_21'])
        if not pd.isna(v['ATR']):
            ctx.atr_14 = float(v['ATR'])
        if not pd.isna(v['ADX']):
            ctx.adx_14 = float(v['ADX'])
        if not pd.isna(v['Plus_DI']):
            ctx.plus_di = float(v['Plus_DI'])
        if not pd.isna(v['Minus_DI']):
            ctx.minus_di = float(v['Minus_DI'])
        if not pd.isna(v['Vol_SMA_20']) and v['Vol_SMA_20'] > 0:
            ctx.volume_ratio = float(v['volume'] / v['Vol_SMA_20'])

        ctx.momentum = float((v['close'] - v_ant['close']) / v_ant['close'])
        ctx.price_change_15m = float((df.iloc[-1]['close'] - df.iloc[-2]['close']) / df.iloc[-2]['close'])

        # Soporte/Resistencia (BB como proxy dinamico)
        ctx.support_price = ctx.bb_lower
        ctx.resistance_price = ctx.bb_upper

    # ── 1h indicators ──
    if velas_1h and len(velas_1h) >= 55:
        df_1h = pd.DataFrame(velas_1h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

        # EMA 50
        df_1h['EMA_50'] = EMAIndicator(close=df_1h['close'], window=50).ema_indicator()
        if not pd.isna(df_1h['EMA_50'].iloc[-1]):
            ctx.ema_50_1h = float(df_1h['EMA_50'].iloc[-1])
            ctx.price_vs_ema50_1h = (precio - ctx.ema_50_1h) / ctx.ema_50_1h

        # EMA 200 (necesita 300 velas)
        if len(df_1h) >= 210:
            df_1h['EMA_200'] = EMAIndicator(close=df_1h['close'], window=200).ema_indicator()
            if not pd.isna(df_1h['EMA_200'].iloc[-1]):
                ctx.ema_200_1h = float(df_1h['EMA_200'].iloc[-1])
                ctx.price_vs_ema200_1h = (precio - ctx.ema_200_1h) / ctx.ema_200_1h

        # ADX + DI en 1h
        if len(df_1h) >= 30:
            adx_1h = ADXIndicator(high=df_1h['high'], low=df_1h['low'], close=df_1h['close'], window=14)
            adx_val = adx_1h.adx().iloc[-1]
            pdi_val = adx_1h.adx_pos().iloc[-1]
            mdi_val = adx_1h.adx_neg().iloc[-1]
            if not pd.isna(adx_val):
                ctx.adx_1h = float(adx_val)
            if not pd.isna(pdi_val):
                ctx.plus_di_1h = float(pdi_val)
            if not pd.isna(mdi_val):
                ctx.minus_di_1h = float(mdi_val)

        # price_change_1h
        if len(df_1h) >= 2:
            ctx.price_change_1h = float(
                (df_1h.iloc[-1]['close'] - df_1h.iloc[-2]['close']) / df_1h.iloc[-2]['close']
            )

        # price_change_24h (24 velas de 1h atras)
        if len(df_1h) >= 25:
            ctx.price_change_24h = float(
                (df_1h.iloc[-1]['close'] - df_1h.iloc[-25]['close']) / df_1h.iloc[-25]['close']
            )

        # Fibonacci (ultimas 48 velas 1h = ~2 dias)
        if len(df_1h) >= 48:
            recent = df_1h.iloc[-48:]
            ctx.swing_high = float(recent['high'].max())
            ctx.swing_low = float(recent['low'].min())
            diff = ctx.swing_high - ctx.swing_low
            if diff > 0:
                ctx.fib_382 = ctx.swing_high - diff * 0.382
                ctx.fib_500 = ctx.swing_high - diff * 0.500
                ctx.fib_618 = ctx.swing_high - diff * 0.618
                ctx.fib_1618 = ctx.swing_low + diff * 1.618

    # ── Weekly RSI ──
    if velas_1w and len(velas_1w) >= 16:
        df_1w = pd.DataFrame(velas_1w, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        rsi_1w = RSIIndicator(close=df_1w['close'], window=14).rsi()
        if not pd.isna(rsi_1w.iloc[-1]):
            ctx.rsi_weekly = float(rsi_1w.iloc[-1])

    return ctx
