import pandas as pd
from ta.trend import EMAIndicator, ADXIndicator
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange
from ta.volume import VolumeWeightedAveragePrice
from ta.volatility import BollingerBands
from modules.logger import logger

class EstrategiaConfluencia:
    def esta_en_consolidacion(self, df, periodos=24, umbral_atr=4.0):
        """
        Verifica si el precio se ha mantenido en un rango estrecho (lateral)
        comparando el rango High-Low contra el ATR.
        """
        if len(df) < periodos: return False
        
        recientes = df.iloc[-periodos:]
        rango_precio = recientes['high'].max() - recientes['low'].min()
        atr_medio = recientes['ATR'].mean()
        
        umbral = atr_medio * umbral_atr
        esta_estable = bool(rango_precio < umbral)
        
        if esta_estable:
            logger.info(f"⚖️ ESTABILIDAD CONFIRMADA | Rango {rango_precio:.2f} < Umbral {umbral:.2f}")
            
        return esta_estable

    def analizar(self, ohlcv_data, rsi_min=25, rsi_max_trend=68, rsi_max_stable=65, skip_log=False):
        """
        Recibe velas y calcula confluencia técnica y estado de estabilidad.
        Permite configurar umbrales RSI para mayor flexibilidad.
        """
        if not ohlcv_data:
            return False, 0.0, False

        df = pd.DataFrame(ohlcv_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # 1. Calcular Indicadores
        df['EMA_50'] = EMAIndicator(close=df['close'], window=50).ema_indicator()
        df['EMA_200'] = EMAIndicator(close=df['close'], window=200).ema_indicator()
        df['RSI_14'] = RSIIndicator(close=df['close'], window=14).rsi()
        df['ATR'] = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14).average_true_range()
        df['ADX'] = ADXIndicator(high=df['high'], low=df['low'], close=df['close'], window=14).adx()
        df['Vol_SMA_20'] = df['volume'].rolling(window=20).mean() # Media Móvil de Volumen
        
        # Evitar datos insuficientes
        if len(df) < 200 or pd.isna(df['EMA_200'].iloc[-1]):
            return False, 0.0, False

        # 2. Evaluar Estabilidad (Consolidación)
        estable = self.esta_en_consolidacion(df)

        # 3. Evaluar Confluencia
        vela_evaluar = df.iloc[-2] # Última vela cerrada
        vela_anterior = df.iloc[-3]
        vela_actual_incompleta = df.iloc[-1]

        # A. Tendencia
        tendencia_alcista_principal = (vela_evaluar['close'] > vela_evaluar['EMA_200'])
        tendencia_local_alcista = (vela_evaluar['close'] > vela_evaluar['EMA_50'])

        # B. Momentum (RSI)
        rango_compra_rsi = (vela_evaluar['RSI_14'] > rsi_min) and (vela_evaluar['RSI_14'] < rsi_max_trend)
        # En modo estable el RSI debe asegurar margen al alza antes de sobrecompra
        rango_compra_rsi_estable = (vela_evaluar['RSI_14'] > rsi_min) and (vela_evaluar['RSI_14'] < rsi_max_stable)
        momento_alcista = (vela_evaluar['RSI_14'] > vela_anterior['RSI_14'])

        # C. Fuerza (ADX)
        fuerza_tendencia = vela_evaluar['ADX'] > 20

        # D. Volumen
        volumen_alto = vela_evaluar['volume'] > (vela_evaluar['Vol_SMA_20'] * 0.8)

        # --- LÓGICA DE SEÑAL FLEXIBLE ---
        if estable:
            # En consolidación también se exige que el RSI esté subiendo para confirmar momentum alcista.
            senal = bool(tendencia_local_alcista and rango_compra_rsi_estable and momento_alcista)
        else:
            senal = bool(tendencia_alcista_principal and rango_compra_rsi and momento_alcista and fuerza_tendencia and volumen_alto)

        atr_actual = float(vela_actual_incompleta['ATR'])

        # FILTRO DE CONTINUIDAD DE PRECIO:
        # Evita entrar cuando el precio en vivo ya cayó respecto al cierre de la vela de señal.
        # Flexibilizado a -0.8% para evitar rechazos masivos de la señal.
        if senal:
            precio_senal = float(vela_evaluar['close'])
            precio_actual_incompleto = float(vela_actual_incompleta['close'])
            caida_vs_senal = (precio_actual_incompleto / precio_senal) - 1
            if caida_vs_senal < -0.008:
                if not skip_log:
                    logger.info(f"⚠️ SEÑAL INVALIDADA: Precio actual {precio_actual_incompleto:.2f} cayó {caida_vs_senal*100:.2f}% vs cierre de señal {precio_senal:.2f}")
                senal = False

        # LOGS DE DIAGNÓSTICO
        if not senal and not skip_log:
            motivos = []
            if estable:
                if not tendencia_local_alcista: motivos.append(f"Tendencia Local (C:{vela_evaluar['close']:.2f} < EMA50:{vela_evaluar['EMA_50']:.1f})")
                if not rango_compra_rsi_estable: motivos.append(f"RSI fuera de rango ({vela_evaluar['RSI_14']:.1f})")
                if not momento_alcista: motivos.append("RSI no sube")
            else:
                if not tendencia_alcista_principal: motivos.append(f"Tendencia (EMA200:{vela_evaluar['EMA_200']:.1f})")
                if not momento_alcista: motivos.append("RSI no sube")
                if not volumen_alto: motivos.append("Volumen bajo")

            if estable or tendencia_alcista_principal:
                logger.info(f"❌ SIN SEÑAL | Motivos: {', '.join(motivos)}")
        elif senal and not skip_log:
             logger.info(f"🚀 SEÑAL DETECTADA ({'ESTABLE' if estable else 'TENDENCIA'}) | RSI: {vela_evaluar['RSI_14']:.1f}")

        return senal, atr_actual, estable

    def esperar_rebote_dca(self, ohlcv_1m):
        """
        Analiza velas muy cortas (1m) para confirmar que el precio
        dejó de caer en caída libre y empezó a rebotar.
        Condición: RSI_7 tocó sobreventa (<30) y ahora está subiendo.
        """
        if not ohlcv_1m or len(ohlcv_1m) < 14:
            return False
            
        df = pd.DataFrame(ohlcv_1m, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['RSI_7'] = RSIIndicator(close=df['close'], window=7).rsi()
        
        if pd.isna(df['RSI_7'].iloc[-2]):
            return False
            
        rsi_actual = df.iloc[-2]['RSI_7']
        rsi_anterior = df.iloc[-3]['RSI_7']
        
        # Está en sobreventa local (<35 para dar margen) y rebotando
        if rsi_actual < 35 and rsi_actual > rsi_anterior:
            vela_actual = df.iloc[-2]
            vela_verde = vela_actual['close'] > vela_actual['open']
            if vela_verde:
                logger.info(f"🪃 REBOTE CONFIRMADO (RSI 1m: {rsi_actual:.1f} ↗)")
                return True
                
        return False


class EstrategiaSmartDCA:
    """
    Estrategia dual de 15m para Smart DCA:
    - MODO 1 (REVERSIÓN): precio < Banda Inferior Bollinger + RSI sobrevendido (<38).
      Ideal para caídas abruptas → promedia con DCA si sigue cayendo.
    - MODO 2 (MOMENTUM): RSI 35-62 subiendo, precio sobre EMA21, impulso positivo.
      Opera en mercados alcistas normales con entrada única conservadora.
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

        # Bloquear solo si estamos MUY por debajo de EMA50 en 1H (>5%)
        if distancia < -0.05:
            logger.info(f"📉 FILTRO MACRO 1H: {precio_actual:.0f} está {distancia*100:.1f}% bajo EMA50_1h {ema50:.0f} | BLOQUEADO")
            return False
        return True
        
    def analizar(self, ohlcv_15m, rsi_oversold=38, rsi_mom_min=35, rsi_mom_max=62, skip_log=False):
        """
        Evalúa señal dual en temporalidad 15m.
        Returns: (bool, float, str|None) -> (hay_señal, atr_actual, modo)
          modo: 'REVERSIÓN' | 'MOMENTUM' | None
        """
        if not ohlcv_15m or len(ohlcv_15m) < 50:
            return False, 0.0, None

        df = pd.DataFrame(ohlcv_15m, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        bollinger = BollingerBands(close=df['close'], window=20, window_dev=2.0)
        df['BB_Lower'] = bollinger.bollinger_lband()
        df['BB_Mid']   = bollinger.bollinger_mavg()
        df['RSI_14']   = RSIIndicator(close=df['close'], window=14).rsi()
        df['EMA_21']   = EMAIndicator(close=df['close'], window=21).ema_indicator()
        df['ATR']      = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14).average_true_range()
        
        v     = df.iloc[-2]  # última vela cerrada 15m
        v_ant = df.iloc[-3]  # penúltima
        
        if pd.isna(v['BB_Lower']) or pd.isna(v['RSI_14']) or pd.isna(v['EMA_21']):
            return False, 0.0, None
            
        atr_actual    = float(df.iloc[-1]['ATR']) if not pd.isna(df.iloc[-1]['ATR']) else float(v['ATR'])
        precio_cierre = float(v['close'])
        bb_inf        = float(v['BB_Lower'])
        rsi           = float(v['RSI_14'])
        rsi_sube      = bool(v['RSI_14'] > v_ant['RSI_14'])
        ema21         = float(v['EMA_21'])
        momentum      = (v['close'] - v_ant['close']) / v_ant['close']

        # ── MODO 1: REVERSIÓN ──────────────────────────────────────────
        # El precio cayó debajo de la Banda Inferior (anomalía estadística)
        # y el RSI está en sobreventa. Señal de compra contraria=alta prob. rebote.
        senal_rev = bool(precio_cierre < bb_inf and rsi < rsi_oversold)

        # ── MODO 2: MOMENTUM ───────────────────────────────────────────
        # Mercado en tendencia normal alcista:
        # RSI en zona sana (no sobrecomprado), subiendo, precio sobre la media.
        senal_mom = bool(
            rsi > rsi_mom_min and rsi < rsi_mom_max
            and rsi_sube
            and precio_cierre > ema21
            and momentum > 0.0008     # impulso mínimo 0.08% por vela
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
            # Diagnóstico reversión
            if precio_cierre >= bb_inf: motivos.append(f"P>{bb_inf:.0f}(BB_Inf)")
            if rsi >= rsi_oversold:     motivos.append(f"RSI={rsi:.1f}≥{rsi_oversold}")
            # Diagnóstico momentum
            if rsi <= rsi_mom_min or rsi >= rsi_mom_max: motivos.append(f"RSI={rsi:.1f} fuera [35-62]")
            if not rsi_sube:            motivos.append("RSI baja")
            if precio_cierre <= ema21:  motivos.append(f"P<EMA21:{ema21:.0f}")
            if momentum <= 0.0008:      motivos.append(f"Mom={momentum*100:.3f}%<0.08%")
            logger.info(f"🔍 15m sin señal | P:{precio_cierre:.2f} BB_Inf:{bb_inf:.2f} RSI:{rsi:.1f} | {' | '.join(motivos)}")
            
        return False, atr_actual, None
