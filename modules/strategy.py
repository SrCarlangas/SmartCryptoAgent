import pandas as pd
from ta.trend import EMAIndicator, ADXIndicator
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange, BollingerBands
from modules.logger import logger
from config import REGIME_PARAMS, SMART_DCA_RSI_TABLE


class EstrategiaSmartDCA:
    """
    Estrategia adaptativa por regimen de mercado.
    - ALCISTA: Trend Following con entradas en retroceso Fibonacci.
    - BAJISTA: Smart DCA agresivo con multiplicador RSI.
    - LATERAL: Mean Reversion en soporte/resistencia.
    - CRASH: Gestionado por orchestrator (protocolo de tranches).

    Mantiene compatibilidad con modos REVERSION y MOMENTUM originales.
    """

    def analizar_filtro_1h(self, ohlcv_1h):
        """Revisa la macro. Evita comprar en desplomes catastroficos sostenidos.
        Retorna True si es seguro operar (precio > EMA50_1h * 0.95).
        """
        if not ohlcv_1h or len(ohlcv_1h) < 55:
            return True  # sin datos: no bloquear

        df = pd.DataFrame(ohlcv_1h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['EMA_50'] = EMAIndicator(close=df['close'], window=50).ema_indicator()

        if pd.isna(df['EMA_50'].iloc[-1]):
            return True

        precio_actual = float(df.iloc[-1]['close'])
        ema50 = float(df.iloc[-1]['EMA_50'])
        distancia = (precio_actual - ema50) / ema50

        if distancia < -0.05:
            logger.info(f"📉 FILTRO MACRO 1H: {precio_actual:.0f} está {distancia*100:.1f}% bajo EMA50_1h {ema50:.0f} | BLOQUEADO")
            return False
        return True

    # ── Punto de entrada principal por regimen ──

    def analizar_por_regimen(self, ohlcv_15m, regime, ctx):
        """Despacha al metodo de analisis segun regimen.
        Returns: (bool, float, str|None) -> (hay_señal, atr_actual, modo)
        """
        if regime == "ALCISTA":
            return self._analizar_alcista(ohlcv_15m, ctx)
        elif regime == "BAJISTA":
            return self._analizar_bajista(ohlcv_15m, ctx)
        elif regime == "LATERAL":
            return self._analizar_lateral(ohlcv_15m, ctx)
        elif regime == "CRASH":
            return False, 0, None  # crash: tranches en orchestrator
        return False, 0, None

    def _analizar_alcista(self, ohlcv_15m, ctx):
        """ALCISTA: Comprar en retroceso Fibonacci 0.382-0.5.
        Requiere RSI 40-55 (pullback sano) y precio > EMA_50_1h.
        """
        if not ohlcv_15m or len(ohlcv_15m) < 50:
            return False, 0.0, None

        df = pd.DataFrame(ohlcv_15m, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['ATR'] = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14).average_true_range()
        df['RSI_14'] = RSIIndicator(close=df['close'], window=14).rsi()

        v = df.iloc[-2]
        if pd.isna(v['RSI_14']) or pd.isna(v['ATR']):
            return False, 0.0, None

        atr = float(df.iloc[-1]['ATR']) if not pd.isna(df.iloc[-1]['ATR']) else float(v['ATR'])
        precio = float(v['close'])
        rsi = float(v['RSI_14'])
        rsi_prev = float(df.iloc[-3]['RSI_14']) if not pd.isna(df.iloc[-3]['RSI_14']) else rsi

        cfg = REGIME_PARAMS["ALCISTA"]

        # Fibonacci: precio entre fib_382 y fib_500
        if ctx.fib_382 > 0 and ctx.fib_500 > 0:
            en_retroceso = ctx.fib_500 <= precio <= ctx.fib_382
        else:
            en_retroceso = False

        # RSI en zona de pullback sano (40-55) y subiendo
        rsi_ok = 40 <= rsi <= 55 and rsi > rsi_prev

        # Precio sobre EMA_50_1h (confirmacion macro alcista)
        macro_ok = ctx.ema_50_1h > 0 and precio > ctx.ema_50_1h

        if en_retroceso and rsi_ok and macro_ok:
            logger.info(
                f"🚀 SEÑAL ALCISTA FIBONACCI | RSI:{rsi:.1f} | "
                f"P:{precio:.2f} en retroceso [{ctx.fib_500:.0f}-{ctx.fib_382:.0f}]"
            )
            return True, atr, "FIBONACCI"

        # Fallback: momentum clasico si no hay retroceso claro
        df['EMA_21'] = EMAIndicator(close=df['close'], window=21).ema_indicator()
        ema21_val = df['EMA_21'].iloc[-2]
        ema21 = float(ema21_val) if not pd.isna(ema21_val) else 0
        momentum = (v['close'] - df.iloc[-3]['close']) / df.iloc[-3]['close']

        if ema21 > 0 and rsi > 35 and rsi < 55 and rsi > rsi_prev and precio > ema21 and momentum > 0.0008 and macro_ok:
            logger.info(f"🚀 SEÑAL ALCISTA MOMENTUM | RSI:{rsi:.1f} | P:{precio:.2f} > EMA21:{ema21:.2f}")
            return True, atr, "MOMENTUM"

        return False, atr, None

    def _analizar_bajista(self, ohlcv_15m, ctx):
        """BAJISTA: Solo señales muy fuertes de reversion. Tamaño reducido 50%."""
        if not ohlcv_15m or len(ohlcv_15m) < 50:
            return False, 0.0, None

        df = pd.DataFrame(ohlcv_15m, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        bollinger = BollingerBands(close=df['close'], window=20, window_dev=2.0)
        df['BB_Lower'] = bollinger.bollinger_lband()
        df['RSI_14'] = RSIIndicator(close=df['close'], window=14).rsi()
        df['ATR'] = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14).average_true_range()

        v = df.iloc[-2]
        if pd.isna(v['RSI_14']) or pd.isna(v['BB_Lower']):
            return False, 0.0, None

        atr = float(df.iloc[-1]['ATR']) if not pd.isna(df.iloc[-1]['ATR']) else float(v['ATR'])
        precio = float(v['close'])
        rsi = float(v['RSI_14'])
        bb_inf = float(v['BB_Lower'])

        # En bajista: reversion fuerte (RSI < 35 + precio < BB_Lower)
        if precio < bb_inf and rsi < 35:
            logger.info(f"🚀 SEÑAL BAJISTA REVERSION | RSI:{rsi:.1f} | P:{precio:.2f} < BB:{bb_inf:.2f}")
            return True, atr, "REVERSION_BEAR"

        return False, atr, None

    def _analizar_lateral(self, ohlcv_15m, ctx):
        """LATERAL: Mean reversion — comprar en soporte RSI<40, vender en resistencia RSI>60."""
        if not ohlcv_15m or len(ohlcv_15m) < 50:
            return False, 0.0, None

        df = pd.DataFrame(ohlcv_15m, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        bollinger = BollingerBands(close=df['close'], window=20, window_dev=2.0)
        df['BB_Lower'] = bollinger.bollinger_lband()
        df['BB_Mid'] = bollinger.bollinger_mavg()
        df['RSI_14'] = RSIIndicator(close=df['close'], window=14).rsi()
        df['EMA_21'] = EMAIndicator(close=df['close'], window=21).ema_indicator()
        df['ATR'] = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14).average_true_range()

        v = df.iloc[-2]
        v_ant = df.iloc[-3]
        if pd.isna(v['RSI_14']) or pd.isna(v['BB_Lower']):
            return False, 0.0, None

        atr = float(df.iloc[-1]['ATR']) if not pd.isna(df.iloc[-1]['ATR']) else float(v['ATR'])
        precio = float(v['close'])
        rsi = float(v['RSI_14'])
        bb_inf = float(v['BB_Lower'])
        rsi_sube = bool(v['RSI_14'] > v_ant['RSI_14'])

        cfg = REGIME_PARAMS["LATERAL"]
        tolerance = cfg["support_tolerance"]

        # Comprar cerca de soporte (BB_Lower ±2%) con RSI < 40
        near_support = precio <= bb_inf * (1 + tolerance)
        if near_support and rsi < cfg["buy_rsi_max"] and rsi_sube:
            logger.info(f"🚀 SEÑAL LATERAL MEAN_REVERSION | RSI:{rsi:.1f} | P:{precio:.2f} cerca BB_Inf:{bb_inf:.2f}")
            return True, atr, "MEAN_REVERSION"

        # Fallback: reversion clasica
        if precio < bb_inf and rsi < 38:
            logger.info(f"🚀 SEÑAL LATERAL REVERSION | RSI:{rsi:.1f} | P:{precio:.2f} < BB:{bb_inf:.2f}")
            return True, atr, "REVERSIÓN"

        # Fallback: momentum en zona media
        ema21 = float(v['EMA_21']) if not pd.isna(v['EMA_21']) else 0
        momentum = (v['close'] - v_ant['close']) / v_ant['close']
        if 35 < rsi < 65 and rsi_sube and precio > ema21 and momentum > 0.0008:
            logger.info(f"🚀 SEÑAL LATERAL MOMENTUM | RSI:{rsi:.1f} | Mom:{momentum*100:.3f}%")
            return True, atr, "MOMENTUM"

        return False, atr, None

    # ── Metodo legacy compatible ──

    def analizar(self, ohlcv_15m, rsi_oversold=38, rsi_mom_min=35, rsi_mom_max=62, skip_log=False):
        """Metodo original dual REVERSION + MOMENTUM (usado como fallback)."""
        if not ohlcv_15m or len(ohlcv_15m) < 50:
            return False, 0.0, None

        df = pd.DataFrame(ohlcv_15m, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        bollinger = BollingerBands(close=df['close'], window=20, window_dev=2.0)
        df['BB_Lower'] = bollinger.bollinger_lband()
        df['BB_Mid'] = bollinger.bollinger_mavg()
        df['RSI_14'] = RSIIndicator(close=df['close'], window=14).rsi()
        df['EMA_21'] = EMAIndicator(close=df['close'], window=21).ema_indicator()
        df['ATR'] = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14).average_true_range()

        v = df.iloc[-2]
        v_ant = df.iloc[-3]

        if pd.isna(v['BB_Lower']) or pd.isna(v['RSI_14']) or pd.isna(v['EMA_21']):
            return False, 0.0, None

        atr_actual = float(df.iloc[-1]['ATR']) if not pd.isna(df.iloc[-1]['ATR']) else float(v['ATR'])
        precio_cierre = float(v['close'])
        bb_inf = float(v['BB_Lower'])
        rsi = float(v['RSI_14'])
        rsi_sube = bool(v['RSI_14'] > v_ant['RSI_14'])
        ema21 = float(v['EMA_21']) if not pd.isna(v['EMA_21']) else 0
        momentum = (v['close'] - v_ant['close']) / v_ant['close']

        senal_rev = bool(precio_cierre < bb_inf and rsi < rsi_oversold)
        senal_mom = bool(
            rsi > rsi_mom_min and rsi < rsi_mom_max
            and rsi_sube
            and precio_cierre > ema21
            and momentum > 0.0008
        )

        if senal_rev:
            if not skip_log:
                logger.info(f"🚀 SEÑAL 15m REVERSIÓN | RSI:{rsi:.1f} | P:{precio_cierre:.2f} < BB_Inf:{bb_inf:.2f}")
            return True, atr_actual, "REVERSIÓN"

        if senal_mom:
            if not skip_log:
                logger.info(f"🚀 SEÑAL 15m MOMENTUM | RSI:{rsi:.1f} | P:{precio_cierre:.2f} > EMA21:{ema21:.2f} | Mom:{momentum*100:.3f}%")
            return True, atr_actual, "MOMENTUM"

        if not skip_log:
            motivos = []
            if precio_cierre >= bb_inf: motivos.append(f"P>{bb_inf:.0f}(BB_Inf)")
            if rsi >= rsi_oversold:     motivos.append(f"RSI={rsi:.1f}≥{rsi_oversold}")
            if rsi <= rsi_mom_min or rsi >= rsi_mom_max: motivos.append(f"RSI={rsi:.1f} fuera [35-62]")
            if not rsi_sube:            motivos.append("RSI baja")
            if precio_cierre <= ema21:  motivos.append(f"P<EMA21:{ema21:.0f}")
            if momentum <= 0.0008:      motivos.append(f"Mom={momentum*100:.3f}%<0.08%")
            logger.info(f"🔍 15m sin señal | P:{precio_cierre:.2f} BB_Inf:{bb_inf:.2f} RSI:{rsi:.1f} | {' | '.join(motivos)}")

        return False, atr_actual, None

    # ── Smart DCA ──

    def get_dca_multiplier(self, rsi, regime):
        """Retorna multiplicador DCA segun RSI y regimen."""
        table = REGIME_PARAMS.get(regime, {}).get("dca_table", SMART_DCA_RSI_TABLE)
        for rsi_max, mult in table:
            if rsi < rsi_max:
                return mult
        return 0.0

    # ── Salidas escalonadas ──

    def evaluar_salidas_escalonadas(self, pos, precio, rsi, regime, weekly_rsi, ctx=None):
        """Evalua triggers de venta parcial. Retorna lista de (trigger_name, sell_pct)."""
        exits = []
        cfg = REGIME_PARAMS.get(regime, {})

        # BAJISTA: momentum reversal exit — proteger ganancias cuando el rally se agota
        if regime == "BAJISTA" and ctx:
            rsi_cayendo = rsi < getattr(ctx, 'rsi_prev', rsi)
            price_retrocede = ctx.price_change_15m < -0.003  # retroceso >0.3% en 15m

            # Caso 1: ROI > 1.2% y momentum cayendo → venta total
            if pos.roi_current > 0.012 and rsi_cayendo and price_retrocede:
                if "bajista_momentum_reversal" not in pos.exits_taken:
                    logger.info(
                        f"📉 BAJISTA MOMENTUM REVERSAL | ROI:{pos.roi_current*100:.2f}% "
                        f"RSI:{rsi:.1f}(cae) | d15m:{ctx.price_change_15m*100:.3f}%"
                    )
                    exits.append(("bajista_momentum_reversal", 1.0))  # venta total
                    return exits

            # Caso 2: Ya hubo partial sell previo y ROI sigue positivo pero cayendo
            # → cerrar el restante para no devolver las ganancias
            has_prior_exit = len(pos.exits_taken) > 0
            if has_prior_exit and pos.roi_current > 0.004 and rsi_cayendo and price_retrocede:
                logger.info(
                    f"📉 BAJISTA EXIT ESCALATION | ROI:{pos.roi_current*100:.2f}% "
                    f"(post-partial) RSI:{rsi:.1f}(cae) | exits_prev:{pos.exits_taken}"
                )
                exits.append(("bajista_exit_escalation", 1.0))  # venta total del restante
                return exits

        # Solo ALCISTA tiene salidas escalonadas configuradas
        if regime == "ALCISTA":
            roi = (precio - pos.entry_price) / pos.entry_price if pos.entry_price > 0 else 0

            for se in cfg.get("scaled_exits", []):
                trigger_name = f"{se['trigger']}_{se.get('value', '')}"
                if trigger_name in pos.exits_taken:
                    continue

                if se["trigger"] == "roi_pct" and roi >= se["value"]:
                    exits.append((trigger_name, se["sell_pct"]))
                elif se["trigger"] == "weekly_rsi_gt" and weekly_rsi > se["value"]:
                    exits.append((trigger_name, se["sell_pct"]))
                elif se["trigger"] == "resistance" and precio >= pos.entry_price * 1.25:
                    # Proxy: si precio > 25% sobre entry, considerar resistencia
                    exits.append((trigger_name, se["sell_pct"]))

            # RSI > 75 → vender 15% (umbral subido de 70 a 75 para aguantar más en ALCISTA)
            if rsi > 75 and "rsi_75_sell" not in pos.exits_taken:
                exits.append(("rsi_75_sell", cfg.get("partial_sell_rsi75", 0.15)))

        # LATERAL: venta parcial en resistencia con RSI > 65 (solo si ROI cubre fees+margen)
        elif regime == "LATERAL":
            if rsi > cfg.get("sell_rsi_min", 65) and pos.roi_current > 0.008:
                if "lateral_resistance_sell" not in pos.exits_taken:
                    exits.append(("lateral_resistance_sell", 0.50))  # 50% parcial, conservar exposición

        return exits
