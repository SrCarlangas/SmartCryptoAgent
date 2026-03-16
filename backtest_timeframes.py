"""
Simulador Multi-Timeframe: 15m (actual) vs 5m vs Híbrido
Objetivo: Encontrar la combinación que maximice ganancia diaria
superando por amplio margen las comisiones de 0.20% round-trip.

Modelo de costos:
  - Comisión compra: 0.10%
  - Comisión venta:  0.10%
  - Total round-trip: 0.20%
  - Con capital de 4400 USDT y 21% por trade (~924 USDT):
    Comisión por trade = 924 * 0.002 = 1.85 USDT
  - Para que un trade sea rentable: ROI neto > 0.20%
  - Margen de seguridad: apuntamos a ROI promedio > 0.50% por trade ganador
"""
import random
import math
import statistics

COMISION_PCT = 0.001  # 0.10% por operación
CAPITAL_INICIAL = 4400.0

# ============================================================
# GENERADOR DE PRECIOS REALISTAS CON MICROESTRUCTURA
# ============================================================

def generar_precios_tick(precio_inicio, duracion_horas, ticks_por_hora, volatilidad_base, tendencia=0, seed=42):
    """
    Genera precios con microestructura realista:
    - Tendencia base
    - Volatilidad variable (clusters)
    - Mean reversion local
    - Momentum de corto plazo
    """
    random.seed(seed)
    precios = [precio_inicio]
    total = duracion_horas * ticks_por_hora

    vol = volatilidad_base
    momentum = 0

    for i in range(total):
        # Volatilidad que cambia (clustering)
        vol = vol * 0.95 + volatilidad_base * 0.05 + abs(random.gauss(0, volatilidad_base * 0.3))

        # Momentum (autocorrelación)
        momentum = momentum * 0.7 + random.gauss(0, vol) * 0.3

        # Cambio = tendencia + momentum + ruido
        cambio = tendencia + momentum + random.gauss(0, vol * 0.5)

        # Mean reversion suave (evitar drift excesivo)
        if len(precios) > 20:
            media_reciente = sum(precios[-20:]) / 20
            reversion = (media_reciente - precios[-1]) / media_reciente * 0.01
            cambio += reversion

        precios.append(precios[-1] * (1 + cambio))

    return precios

def generar_escenarios_multitf():
    """Genera escenarios con resolución de 1 minuto (muestreamos para 5m y 15m)"""
    escenarios = {}

    # 1. Alcista gradual (1m resolution, 24h = 1440 ticks)
    escenarios['Alcista +2%'] = generar_precios_tick(
        69000, 24, 60, 0.0004, tendencia=0.000015, seed=42
    )

    # 2. Alcista fuerte (+4%)
    escenarios['Alcista +4%'] = generar_precios_tick(
        68000, 24, 60, 0.0005, tendencia=0.00003, seed=43
    )

    # 3. Bajista suave (-2%)
    escenarios['Bajista -2%'] = generar_precios_tick(
        71000, 24, 60, 0.0004, tendencia=-0.000015, seed=44
    )

    # 4. Bajista fuerte (-4%)
    escenarios['Bajista -4%'] = generar_precios_tick(
        72000, 24, 60, 0.0005, tendencia=-0.00003, seed=45
    )

    # 5. Lateral estrecho
    escenarios['Lateral 1%'] = generar_precios_tick(
        70000, 24, 60, 0.0003, tendencia=0, seed=46
    )

    # 6. Lateral amplio
    escenarios['Lateral 3%'] = generar_precios_tick(
        70000, 24, 60, 0.0006, tendencia=0, seed=47
    )

    # 7. Crash y rebote
    random.seed(48)
    p = [71000]
    for _ in range(360):  # 6h subida
        p.append(p[-1] * (1 + random.gauss(0.00005, 0.0004)))
    for _ in range(180):  # 3h crash
        p.append(p[-1] * (1 + random.gauss(-0.00025, 0.0005)))
    for _ in range(180):  # 3h fondo
        p.append(p[-1] * (1 + random.gauss(0, 0.0004)))
    for _ in range(360):  # 6h recuperación
        p.append(p[-1] * (1 + random.gauss(0.00008, 0.0004)))
    for _ in range(1440 - len(p) + 1):
        p.append(p[-1] * (1 + random.gauss(0.00002, 0.0003)))
    escenarios['Crash+Rebote'] = p

    # 8. Dientes de sierra (ideal para scalping)
    random.seed(49)
    p = [70000]
    for ciclo in range(8):  # 8 ciclos de 3h
        # Subida 1.5h (90 min)
        for _ in range(90):
            p.append(p[-1] * (1 + random.gauss(0.0001, 0.0003)))
        # Bajada 1.5h
        for _ in range(90):
            p.append(p[-1] * (1 + random.gauss(-0.00008, 0.0003)))
    escenarios['Dientes Sierra'] = p[:1441]

    # 9. Volatilidad extrema
    escenarios['Vol. Extrema'] = generar_precios_tick(
        70000, 24, 60, 0.0008, tendencia=0, seed=50
    )

    # 10. Patrón real Mar 10
    random.seed(51)
    p = [69000]
    # 00:00-02:00 lateral
    for _ in range(120):
        p.append(p[-1] * (1 + random.gauss(0, 0.0003)))
    # 02:00-05:00 subida a 70200
    for _ in range(180):
        p.append(p[-1] * (1 + random.gauss(0.00005, 0.0003)))
    # 05:00-09:00 sube a 71000
    for _ in range(240):
        p.append(p[-1] * (1 + random.gauss(0.00003, 0.0004)))
    # 09:00-13:00 lateral/bajando
    for _ in range(240):
        p.append(p[-1] * (1 + random.gauss(-0.00002, 0.0004)))
    # 13:00-18:00 caída a 69500
    for _ in range(300):
        p.append(p[-1] * (1 + random.gauss(-0.00005, 0.0004)))
    # 18:00-24:00 lenta recuperación
    for _ in range(1440 - len(p) + 1):
        p.append(p[-1] * (1 + random.gauss(0.00003, 0.0004)))
    escenarios['Patron Real BTC'] = p[:1441]

    return escenarios


def muestrear(precios_1m, intervalo_min):
    """Submuestrear precios de 1m a intervalos mayores (cierre de cada vela)"""
    return [precios_1m[i] for i in range(0, len(precios_1m), intervalo_min)]


# ============================================================
# INDICADORES SIMPLIFICADOS
# ============================================================

def calc_rsi(precios, periodo=14):
    """RSI sobre lista de precios"""
    if len(precios) < periodo + 1:
        return 50
    gains = losses = 0
    for i in range(-periodo, 0):
        diff = precios[i] - precios[i-1]
        if diff > 0:
            gains += diff
        else:
            losses -= diff
    if losses == 0:
        return 100
    if gains == 0:
        return 0
    rs = gains / losses
    return 100 - (100 / (1 + rs))

def calc_ema(precios, periodo):
    """EMA del último valor"""
    if len(precios) < periodo:
        return precios[-1]
    k = 2 / (periodo + 1)
    ema = precios[-periodo]
    for p in precios[-periodo+1:]:
        ema = p * k + ema * (1 - k)
    return ema

def momentum_score(precios, lookback=5):
    """Score de momentum: positivo = subiendo, negativo = bajando"""
    if len(precios) < lookback + 1:
        return 0
    return (precios[-1] - precios[-lookback-1]) / precios[-lookback-1]


# ============================================================
# ESTRATEGIAS
# ============================================================

class Estrategia15m:
    """Estrategia DCA actual optimizada en 15m"""
    def __init__(self, params):
        self.p = params
        self.reset()

    def reset(self):
        self.capital = CAPITAL_INICIAL
        self.in_pos = False
        self.entry = 0
        self.qty = 0
        self.invested = 0
        self.dca_done = False
        self.trailing = False
        self.high = 0
        self.ticks = 0
        self.trades = []
        self.fees = 0
        self.cooldown = 0

    def step(self, precios_hist, precio_actual, precios_1m_recientes=None):
        if self.cooldown > 0:
            self.cooldown -= 1
            return

        if self.in_pos:
            self.ticks += 1
            roi = (precio_actual - self.entry) / self.entry
            vender = False
            motivo = ""

            # Trailing
            if roi >= self.p['tp']:
                if not self.trailing:
                    self.trailing = True
                    self.high = precio_actual
                else:
                    self.high = max(self.high, precio_actual)
                if precio_actual <= self.high * (1 - self.p['trail']):
                    vender = True
                    motivo = f"TRAIL +{roi*100:.2f}%"

            # SL
            if not vender and roi <= -self.p['sl']:
                vender = True
                motivo = f"SL {roi*100:.2f}%"

            # Timeout
            if not vender and self.ticks >= self.p.get('max_ticks', 999):
                if roi > -self.p['sl'] * 0.7:
                    vender = True
                    motivo = f"TIMEOUT {roi*100:.2f}%"

            # DCA
            if not vender and not self.trailing and not self.dca_done:
                if roi <= self.p.get('dca_drop', -0.01):
                    cap_dca = CAPITAL_INICIAL * self.p['exposure'] * self.p.get('dca_alloc', 0.20)
                    cap_dca = min(cap_dca, self.capital * 0.95)
                    if cap_dca > 10:
                        fee = cap_dca * COMISION_PCT
                        self.fees += fee
                        q = (cap_dca - fee) / precio_actual
                        old_q, old_e = self.qty, self.entry
                        self.qty += q
                        self.entry = (old_q * old_e + q * precio_actual) / self.qty
                        self.invested += cap_dca
                        self.capital -= cap_dca
                        self.dca_done = True
                        self.trailing = False
                        self.high = 0

            if vender:
                bruto = precio_actual * self.qty
                fee = bruto * COMISION_PCT
                self.fees += fee
                neto = bruto - fee
                profit = neto - self.invested
                self.capital += neto
                self.trades.append({'roi': roi*100, 'profit': profit, 'motivo': motivo, 'ticks': self.ticks})
                self.in_pos = False
                self.qty = 0
                self.invested = 0
                self.dca_done = False
                self.trailing = False
                self.high = 0
                self.ticks = 0
                if 'SL' in motivo:
                    self.cooldown = self.p.get('cooldown', 4)

        else:
            # Señal de entrada
            if len(precios_hist) < 30:
                return
            rsi = calc_rsi(precios_hist, 14)
            ema50 = calc_ema(precios_hist, min(50, len(precios_hist)))
            mom = momentum_score(precios_hist, 3)

            rsi_ok = self.p['rsi_min'] <= rsi <= self.p['rsi_max']
            trend_ok = precio_actual > ema50 * 0.998
            mom_ok = mom > 0

            if rsi_ok and trend_ok and mom_ok:
                cap = CAPITAL_INICIAL * self.p['exposure'] * self.p['base_alloc']
                cap = min(cap, self.capital * 0.95)
                if cap > 10:
                    fee = cap * COMISION_PCT
                    self.fees += fee
                    q = (cap - fee) / precio_actual
                    self.in_pos = True
                    self.entry = precio_actual
                    self.qty = q
                    self.invested = cap
                    self.capital -= cap
                    self.dca_done = False
                    self.trailing = False
                    self.high = 0
                    self.ticks = 0

    def cerrar(self, precio):
        if self.in_pos:
            roi = (precio - self.entry) / self.entry
            bruto = precio * self.qty
            fee = bruto * COMISION_PCT
            self.fees += fee
            self.capital += bruto - fee
            self.trades.append({'roi': roi*100, 'profit': bruto-fee-self.invested, 'motivo': 'CIERRE', 'ticks': self.ticks})
            self.in_pos = False


class Estrategia5m:
    """Estrategia en 5m: Más trades, TP/SL más ajustados"""
    def __init__(self, params):
        self.p = params
        self.reset()

    def reset(self):
        self.capital = CAPITAL_INICIAL
        self.in_pos = False
        self.entry = 0
        self.qty = 0
        self.invested = 0
        self.trailing = False
        self.high = 0
        self.ticks = 0
        self.trades = []
        self.fees = 0
        self.cooldown = 0

    def step(self, precios_hist_5m, precio_actual, precios_hist_15m=None):
        if self.cooldown > 0:
            self.cooldown -= 1
            return

        if self.in_pos:
            self.ticks += 1
            roi = (precio_actual - self.entry) / self.entry
            vender = False
            motivo = ""

            # Trailing TP
            if roi >= self.p['tp']:
                if not self.trailing:
                    self.trailing = True
                    self.high = precio_actual
                else:
                    self.high = max(self.high, precio_actual)
                if precio_actual <= self.high * (1 - self.p['trail']):
                    vender = True
                    motivo = f"TRAIL +{roi*100:.2f}%"

            # SL
            if not vender and roi <= -self.p['sl']:
                vender = True
                motivo = f"SL {roi*100:.2f}%"

            # Timeout
            if not vender and self.ticks >= self.p.get('max_ticks', 999):
                if roi > -self.p['sl'] * 0.5:
                    vender = True
                    motivo = f"TIMEOUT {roi*100:.2f}%"

            if vender:
                bruto = precio_actual * self.qty
                fee = bruto * COMISION_PCT
                self.fees += fee
                neto = bruto - fee
                profit = neto - self.invested
                self.capital += neto
                self.trades.append({'roi': roi*100, 'profit': profit, 'motivo': motivo, 'ticks': self.ticks})
                self.in_pos = False
                self.qty = 0
                self.invested = 0
                self.trailing = False
                self.high = 0
                self.ticks = 0
                if 'SL' in motivo:
                    self.cooldown = self.p.get('cooldown', 3)
                else:
                    self.cooldown = self.p.get('cooldown_win', 1)

        else:
            if len(precios_hist_5m) < 25:
                return

            rsi7 = calc_rsi(precios_hist_5m, 7)
            rsi14 = calc_rsi(precios_hist_5m, 14)
            ema21 = calc_ema(precios_hist_5m, 21)
            mom = momentum_score(precios_hist_5m, 3)

            # Filtro de tendencia 15m (si disponible)
            trend_15m_ok = True
            if precios_hist_15m and len(precios_hist_15m) > 20:
                ema50_15m = calc_ema(precios_hist_15m, min(50, len(precios_hist_15m)))
                trend_15m_ok = precio_actual > ema50_15m * (1 - self.p.get('trend_tolerance', 0.005))

            # Condiciones de entrada
            señal = False

            if self.p.get('mode') == 'oversold_bounce':
                # Comprar cuando RSI7 está en sobreventa y empezando a subir
                señal = (rsi7 < self.p.get('rsi_oversold', 35) and
                        mom > 0 and
                        precio_actual < ema21 and
                        trend_15m_ok)

            elif self.p.get('mode') == 'momentum':
                # Comprar en momentum alcista con RSI en rango medio
                señal = (self.p['rsi_min'] <= rsi14 <= self.p['rsi_max'] and
                        mom > 0 and
                        precio_actual > ema21 and
                        trend_15m_ok)

            elif self.p.get('mode') == 'hybrid':
                # Oversold bounce O momentum, pero con filtros más estrictos
                oversold = (rsi7 < 32 and mom > 0 and precio_actual < ema21)
                momentum = (self.p['rsi_min'] <= rsi14 <= self.p['rsi_max'] and
                           mom > self.p.get('min_mom', 0.0005) and
                           precio_actual > ema21)
                señal = trend_15m_ok and (oversold or momentum)

            if señal:
                cap = CAPITAL_INICIAL * self.p['exposure'] * self.p['base_alloc']
                cap = min(cap, self.capital * 0.95)
                if cap > 10:
                    fee = cap * COMISION_PCT
                    self.fees += fee
                    q = (cap - fee) / precio_actual
                    self.in_pos = True
                    self.entry = precio_actual
                    self.qty = q
                    self.invested = cap
                    self.capital -= cap
                    self.trailing = False
                    self.high = 0
                    self.ticks = 0

    def cerrar(self, precio):
        if self.in_pos:
            roi = (precio - self.entry) / self.entry
            bruto = precio * self.qty
            fee = bruto * COMISION_PCT
            self.fees += fee
            self.capital += bruto - fee
            self.trades.append({'roi': roi*100, 'profit': bruto-fee-self.invested, 'motivo': 'CIERRE', 'ticks': self.ticks})
            self.in_pos = False


# ============================================================
# CONFIGURACIONES A PROBAR
# ============================================================

CONFIGS = {
    # --- BASELINE: 15m actual optimizado ---
    '15m Actual Optimizado': {
        'type': '15m',
        'exposure': 0.70, 'base_alloc': 0.30,
        'tp': 0.010, 'trail': 0.0035, 'sl': 0.018,
        'dca_drop': -0.010, 'dca_alloc': 0.20,
        'max_ticks': 40, 'cooldown': 8,
        'rsi_min': 25, 'rsi_max': 65,
    },

    # --- 5m: Oversold Bounce (comprar caídas) ---
    '5m Oversold Bounce': {
        'type': '5m',
        'mode': 'oversold_bounce',
        'exposure': 0.70, 'base_alloc': 0.30,
        'tp': 0.006, 'trail': 0.0025, 'sl': 0.008,
        'rsi_oversold': 35,
        'max_ticks': 36,  # 3h max
        'cooldown': 6, 'cooldown_win': 2,
        'rsi_min': 25, 'rsi_max': 60,
        'trend_tolerance': 0.005,
    },

    # --- 5m: Momentum (seguir tendencia) ---
    '5m Momentum': {
        'type': '5m',
        'mode': 'momentum',
        'exposure': 0.70, 'base_alloc': 0.30,
        'tp': 0.007, 'trail': 0.003, 'sl': 0.008,
        'max_ticks': 24,  # 2h max
        'cooldown': 4, 'cooldown_win': 1,
        'rsi_min': 35, 'rsi_max': 65,
        'trend_tolerance': 0.003,
    },

    # --- 5m: Híbrido (oversold + momentum) ---
    '5m Hibrido': {
        'type': '5m',
        'mode': 'hybrid',
        'exposure': 0.70, 'base_alloc': 0.30,
        'tp': 0.007, 'trail': 0.003, 'sl': 0.009,
        'max_ticks': 30,  # 2.5h max
        'cooldown': 5, 'cooldown_win': 1,
        'rsi_min': 35, 'rsi_max': 62,
        'min_mom': 0.0003,
        'trend_tolerance': 0.004,
    },

    # --- 5m: TP Alto (dejar correr ganadores) ---
    '5m TP Alto (Runner)': {
        'type': '5m',
        'mode': 'hybrid',
        'exposure': 0.70, 'base_alloc': 0.30,
        'tp': 0.010, 'trail': 0.004, 'sl': 0.010,
        'max_ticks': 48,  # 4h max
        'cooldown': 6, 'cooldown_win': 2,
        'rsi_min': 30, 'rsi_max': 60,
        'min_mom': 0.0004,
        'trend_tolerance': 0.005,
    },

    # --- 5m: Sniper (TP bajo, muchos trades) ---
    '5m Sniper (Rapido)': {
        'type': '5m',
        'mode': 'hybrid',
        'exposure': 0.75, 'base_alloc': 0.35,
        'tp': 0.005, 'trail': 0.002, 'sl': 0.006,
        'max_ticks': 18,  # 1.5h max
        'cooldown': 3, 'cooldown_win': 1,
        'rsi_min': 30, 'rsi_max': 68,
        'min_mom': 0.0002,
        'trend_tolerance': 0.006,
    },

    # --- 5m: Posición Grande ---
    '5m PosGrande Hibrido': {
        'type': '5m',
        'mode': 'hybrid',
        'exposure': 0.85, 'base_alloc': 0.40,
        'tp': 0.007, 'trail': 0.003, 'sl': 0.009,
        'max_ticks': 30,
        'cooldown': 6, 'cooldown_win': 1,
        'rsi_min': 30, 'rsi_max': 65,
        'min_mom': 0.0003,
        'trend_tolerance': 0.005,
    },

    # --- 5m: SL Ultra Ajustado ---
    '5m SL Ajustado': {
        'type': '5m',
        'mode': 'hybrid',
        'exposure': 0.70, 'base_alloc': 0.30,
        'tp': 0.006, 'trail': 0.0025, 'sl': 0.005,
        'max_ticks': 24,
        'cooldown': 4, 'cooldown_win': 1,
        'rsi_min': 30, 'rsi_max': 65,
        'min_mom': 0.0003,
        'trend_tolerance': 0.004,
    },
}


# ============================================================
# MOTOR DE SIMULACIÓN
# ============================================================

def simular(nombre, config, precios_1m, seed_offset=0):
    """Simula una estrategia sobre precios de 1 minuto"""

    if config['type'] == '15m':
        precios_tf = muestrear(precios_1m, 15)
        strat = Estrategia15m(config)

        for i in range(len(precios_tf)):
            hist = precios_tf[max(0, i-100):i+1]
            strat.step(hist, precios_tf[i])

        strat.cerrar(precios_tf[-1])
        return strat

    elif config['type'] == '5m':
        precios_5m = muestrear(precios_1m, 5)
        precios_15m = muestrear(precios_1m, 15)
        strat = Estrategia5m(config)

        for i in range(len(precios_5m)):
            hist_5m = precios_5m[max(0, i-100):i+1]
            # Correspondencia 5m -> 15m (cada 3 velas de 5m = 1 de 15m)
            idx_15m = min(i // 3, len(precios_15m) - 1)
            hist_15m = precios_15m[max(0, idx_15m-50):idx_15m+1]
            strat.step(hist_5m, precios_5m[i], hist_15m)

        strat.cerrar(precios_5m[-1])
        return strat


def main():
    escenarios = generar_escenarios_multitf()
    NUM_RUNS = 30

    print("=" * 140)
    print("SIMULADOR MULTI-TIMEFRAME: 15m vs 5m vs Híbrido")
    print(f"Capital: {CAPITAL_INICIAL:.0f} USDT | Comisión: 0.10%/op (0.20% round-trip)")
    print(f"Resolución base: 1 minuto | Duración: 24h | Runs por escenario: {NUM_RUNS}")
    print("=" * 140)

    # Almacenar resultados globales
    global_data = {name: [] for name in CONFIGS}

    for esc_name, precios_base in escenarios.items():
        print(f"\n{'─' * 140}")
        print(f"📊 {esc_name} | Rango: {min(precios_base):.0f}-{max(precios_base):.0f} ({(max(precios_base)/min(precios_base)-1)*100:.1f}%)")
        print(f"{'─' * 140}")
        print(f"{'Estrategia':<28} {'Ret%':>7} {'#Trades':>8} {'WR%':>6} {'AvgWin%':>8} {'AvgLoss%':>9} {'NetROI/T':>9} {'Fees$':>7} {'P&L$':>8} {'DD%':>6} {'$/h':>6}")
        print(f"{'─'*28} {'─'*7} {'─'*8} {'─'*6} {'─'*8} {'─'*9} {'─'*9} {'─'*7} {'─'*8} {'─'*6} {'─'*6}")

        for cfg_name, cfg in CONFIGS.items():
            rets = []
            trades_list = []
            wrs = []
            avg_wins = []
            avg_losses = []
            fees_list = []
            dds = []

            for run in range(NUM_RUNS):
                # Añadir variación
                random.seed(42 + run * 71 + hash(esc_name) % 500)
                precios = [p * (1 + random.gauss(0, 0.0002)) for p in precios_base]

                strat = simular(cfg_name, cfg, precios, seed_offset=run)

                ret = (strat.capital - CAPITAL_INICIAL) / CAPITAL_INICIAL * 100
                rets.append(ret)
                trades_list.append(len(strat.trades))
                wins = [t for t in strat.trades if t['profit'] > 0]
                losses = [t for t in strat.trades if t['profit'] <= 0]
                wr = len(wins) / len(strat.trades) * 100 if strat.trades else 0
                wrs.append(wr)
                avg_wins.append(statistics.mean([t['roi'] for t in wins]) if wins else 0)
                avg_losses.append(statistics.mean([t['roi'] for t in losses]) if losses else 0)
                fees_list.append(strat.fees)

                # Max drawdown
                peak = CAPITAL_INICIAL
                max_dd = 0
                cap = CAPITAL_INICIAL
                for t in strat.trades:
                    cap += t['profit']
                    peak = max(peak, cap)
                    dd = (peak - cap) / peak
                    max_dd = max(max_dd, dd)
                dds.append(max_dd * 100)

                global_data[cfg_name].append(ret)

            ar = statistics.mean(rets)
            at = statistics.mean(trades_list)
            awr = statistics.mean(wrs)
            aw = statistics.mean(avg_wins)
            al = statistics.mean(avg_losses)
            af = statistics.mean(fees_list)
            add = statistics.mean(dds)
            pnl = ar * CAPITAL_INICIAL / 100
            net_per_trade = ar / max(at, 0.1)
            per_hour = pnl / 24

            print(f"{cfg_name:<28} {ar:>+6.2f}% {at:>7.1f} {awr:>5.1f}% {aw:>+7.2f}% {al:>+8.2f}% {net_per_trade:>+8.3f}% {af:>6.2f} {pnl:>+7.2f} {add:>5.2f}% {per_hour:>+5.2f}")

    # ============================================================
    # RESUMEN GLOBAL
    # ============================================================
    print(f"\n{'=' * 140}")
    print("🏆 RESUMEN GLOBAL (PROMEDIO TODOS LOS ESCENARIOS)")
    print(f"{'=' * 140}")
    print(f"{'Estrategia':<28} {'Ret%':>7} {'P&L$':>8} {'Consist.':>9} {'WorsCase':>9} {'BestCase':>9} {'Sharpe':>7} {'Rank':>5}")
    print(f"{'─'*28} {'─'*7} {'─'*8} {'─'*9} {'─'*9} {'─'*9} {'─'*7} {'─'*5}")

    ranking = []
    for cfg_name in CONFIGS:
        datos = global_data[cfg_name]
        n = len(datos)
        avg = statistics.mean(datos)
        std = statistics.stdev(datos) if n > 1 else 0.01
        pnl = avg * CAPITAL_INICIAL / 100
        worst = min(datos)
        best = max(datos)
        sharpe = avg / std if std > 0 else 0
        # Score: retorno * consistencia - peor caso
        positivos = sum(1 for d in datos if d > 0) / n * 100
        score = sharpe - (abs(worst) * 0.05)

        ranking.append((cfg_name, avg, pnl, positivos, worst, best, sharpe, score))

    ranking.sort(key=lambda x: x[7], reverse=True)

    for i, (name, avg, pnl, pos, worst, best, sharpe, score) in enumerate(ranking):
        medal = ['🥇', '🥈', '🥉'][i] if i < 3 else f'{i+1}.'
        print(f"{name:<28} {avg:>+6.2f}% {pnl:>+7.2f} {pos:>7.1f}% {worst:>+8.2f}% {best:>+8.2f}% {sharpe:>+6.2f} {medal:>4}")

    # Ganador
    winner = ranking[0]
    print(f"\n{'=' * 140}")
    print(f"⭐ MEJOR ESTRATEGIA: {winner[0]}")
    print(f"   Retorno diario promedio: {winner[1]:+.2f}% ({winner[2]:+.2f} USDT)")
    print(f"   Días positivos: {winner[3]:.1f}%")
    print(f"   Peor día: {winner[4]:+.2f}% | Mejor día: {winner[5]:+.2f}%")
    print(f"   Sharpe: {winner[6]:+.2f}")
    print(f"{'=' * 140}")

    # Detalle del ganador por escenario
    winner_name = winner[0]
    winner_cfg = CONFIGS[winner_name]
    print(f"\n📋 Detalle del ganador: {winner_name}")
    for esc_name, precios_base in escenarios.items():
        random.seed(42)
        precios = list(precios_base)
        strat = simular(winner_name, winner_cfg, precios)
        ret = (strat.capital - CAPITAL_INICIAL) / CAPITAL_INICIAL * 100
        print(f"\n  {esc_name}: {ret:+.2f}% | {len(strat.trades)} trades | Fees: {strat.fees:.2f}")
        for t in strat.trades[:8]:
            win = "W" if t['profit'] > 0 else "L"
            print(f"    [{win}] ROI:{t['roi']:>+5.2f}% | ${t['profit']:>+7.2f} | {t['ticks']:>3}t | {t['motivo']}")

    # ============================================================
    # ANÁLISIS: MARGEN SOBRE COMISIONES
    # ============================================================
    print(f"\n{'=' * 140}")
    print("📊 ANÁLISIS DE MARGEN SOBRE COMISIONES")
    print(f"{'=' * 140}")
    print(f"  Comisión round-trip: 0.20% del capital por trade")
    print(f"  Con ~{CAPITAL_INICIAL*0.70*0.30:.0f} USDT por trade: {CAPITAL_INICIAL*0.70*0.30*0.002:.2f} USDT de comisión/trade")
    print()

    for cfg_name in CONFIGS:
        datos = global_data[cfg_name]
        avg_ret = statistics.mean(datos)
        # Estimar trades/día promedio
        total_trades = 0
        total_runs = 0
        for esc_name, precios_base in escenarios.items():
            for run in range(3):
                random.seed(42 + run * 71 + hash(esc_name) % 500)
                precios = [p * (1 + random.gauss(0, 0.0002)) for p in precios_base]
                strat = simular(cfg_name, CONFIGS[cfg_name], precios, seed_offset=run)
                total_trades += len(strat.trades)
                total_runs += 1
        avg_trades = total_trades / total_runs if total_runs > 0 else 0
        cost_per_day = avg_trades * CAPITAL_INICIAL * CONFIGS[cfg_name]['exposure'] * CONFIGS[cfg_name]['base_alloc'] * 0.002
        gross_ret = avg_ret + (cost_per_day / CAPITAL_INICIAL * 100)

        margen = "AMPLIO" if avg_ret > 0.3 else "OK" if avg_ret > 0.05 else "MARGINAL" if avg_ret > -0.1 else "NEGATIVO"
        print(f"  {cfg_name:<28} | Bruto:{gross_ret:>+5.2f}% - Comisiones:{cost_per_day:>5.2f}$ = Neto:{avg_ret:>+5.2f}% | Trades/d:{avg_trades:.1f} | {margen}")


if __name__ == '__main__':
    main()
