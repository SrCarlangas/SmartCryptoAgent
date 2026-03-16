"""
Simulador de Backtesting para optimizar la estrategia DCA del bot.
Simula múltiples escenarios de mercado (alza, baja, lateral, crash, rebote)
y prueba diferentes combinaciones de parámetros para encontrar los óptimos.

Objetivo: 2% diario neto después de comisiones (0.10% compra + 0.10% venta).
"""
import random
import math
import itertools

# ============================================================
# GENERADORES DE ESCENARIOS DE MERCADO
# ============================================================

def generar_precios_tendencia_alcista(precio_inicio=69000, duracion_horas=24, volatilidad=0.002, tendencia=0.0004):
    """Mercado alcista gradual con volatilidad normal"""
    precios = [precio_inicio]
    ticks_por_hora = 4  # 15 min candles
    total = duracion_horas * ticks_por_hora
    for i in range(total):
        cambio = random.gauss(tendencia, volatilidad)
        precios.append(precios[-1] * (1 + cambio))
    return precios

def generar_precios_tendencia_bajista(precio_inicio=71000, duracion_horas=24, volatilidad=0.002, tendencia=-0.0003):
    """Mercado bajista gradual"""
    precios = [precio_inicio]
    ticks_por_hora = 4
    total = duracion_horas * ticks_por_hora
    for i in range(total):
        cambio = random.gauss(tendencia, volatilidad)
        precios.append(precios[-1] * (1 + cambio))
    return precios

def generar_precios_lateral(precio_inicio=70000, duracion_horas=24, volatilidad=0.0025, rango_pct=0.02):
    """Mercado lateral/consolidación oscilando en un rango"""
    precios = [precio_inicio]
    ticks_por_hora = 4
    total = duracion_horas * ticks_por_hora
    centro = precio_inicio
    for i in range(total):
        cambio = random.gauss(0, volatilidad)
        nuevo = precios[-1] * (1 + cambio)
        # Revertir al centro si se aleja demasiado
        if nuevo > centro * (1 + rango_pct):
            nuevo = precios[-1] * (1 - abs(cambio))
        elif nuevo < centro * (1 - rango_pct):
            nuevo = precios[-1] * (1 + abs(cambio))
        precios.append(nuevo)
    return precios

def generar_precios_crash_y_rebote(precio_inicio=71000, duracion_horas=24):
    """Crash rápido seguido de recuperación parcial"""
    precios = [precio_inicio]
    ticks_por_hora = 4
    total = duracion_horas * ticks_por_hora

    # Fase 1: Caída rápida (3h = 12 ticks) - cae ~4%
    for i in range(12):
        cambio = random.gauss(-0.0035, 0.001)
        precios.append(precios[-1] * (1 + cambio))

    # Fase 2: Consolidación en el fondo (4h = 16 ticks)
    for i in range(16):
        cambio = random.gauss(0.0001, 0.002)
        precios.append(precios[-1] * (1 + cambio))

    # Fase 3: Recuperación gradual (8h = 32 ticks) - recupera ~2.5%
    for i in range(32):
        cambio = random.gauss(0.0008, 0.0015)
        precios.append(precios[-1] * (1 + cambio))

    # Fase 4: Nuevo lateral (resto del día)
    restante = total - 12 - 16 - 32
    for i in range(max(0, restante)):
        cambio = random.gauss(0.0001, 0.002)
        precios.append(precios[-1] * (1 + cambio))

    return precios

def generar_precios_pump_and_dump(precio_inicio=69000, duracion_horas=24):
    """Subida rápida y caída abrupta"""
    precios = [precio_inicio]
    ticks_por_hora = 4
    total = duracion_horas * ticks_por_hora

    # Fase 1: Pump (4h = 16 ticks) +3%
    for i in range(16):
        cambio = random.gauss(0.002, 0.001)
        precios.append(precios[-1] * (1 + cambio))

    # Fase 2: Dump (2h = 8 ticks) -4%
    for i in range(8):
        cambio = random.gauss(-0.005, 0.002)
        precios.append(precios[-1] * (1 + cambio))

    # Fase 3: Recuperación lenta
    restante = total - 16 - 8
    for i in range(max(0, restante)):
        cambio = random.gauss(0.0003, 0.002)
        precios.append(precios[-1] * (1 + cambio))

    return precios

def generar_precios_volatilidad_extrema(precio_inicio=70000, duracion_horas=24):
    """Alta volatilidad sin dirección clara"""
    precios = [precio_inicio]
    ticks_por_hora = 4
    total = duracion_horas * ticks_por_hora
    for i in range(total):
        cambio = random.gauss(0, 0.005)  # Volatilidad 2.5x normal
        precios.append(precios[-1] * (1 + cambio))
    return precios

def generar_precios_escalera_alcista(precio_inicio=68000, duracion_horas=24):
    """Subidas escalonadas con retrocesos pequeños"""
    precios = [precio_inicio]
    ticks_por_hora = 4
    total = duracion_horas * ticks_por_hora
    ciclo = 0
    for i in range(total):
        fase = i % 16  # Ciclo de 4 horas
        if fase < 10:  # 2.5h subiendo
            cambio = random.gauss(0.0006, 0.001)
        else:  # 1.5h retrocediendo
            cambio = random.gauss(-0.0003, 0.0012)
        precios.append(precios[-1] * (1 + cambio))
    return precios

def generar_precios_real_btc_marzo(precio_inicio=69000, duracion_horas=24):
    """Simula el patrón real observado: subida matutina, caída vespertina, recuperación"""
    precios = [precio_inicio]
    ticks_por_hora = 4
    total = duracion_horas * ticks_por_hora

    # 00:00-04:00: Subida moderada (+1.5%)
    for i in range(16):
        cambio = random.gauss(0.001, 0.0015)
        precios.append(precios[-1] * (1 + cambio))

    # 04:00-08:00: Continuación alcista suave (+1%)
    for i in range(16):
        cambio = random.gauss(0.0006, 0.002)
        precios.append(precios[-1] * (1 + cambio))

    # 08:00-13:00: Lateral con sesgo bajista
    for i in range(20):
        cambio = random.gauss(-0.0001, 0.002)
        precios.append(precios[-1] * (1 + cambio))

    # 13:00-15:00: Caída (-2%)
    for i in range(8):
        cambio = random.gauss(-0.0025, 0.0015)
        precios.append(precios[-1] * (1 + cambio))

    # 15:00-18:00: Más caída (-1.5%)
    for i in range(12):
        cambio = random.gauss(-0.0012, 0.002)
        precios.append(precios[-1] * (1 + cambio))

    # 18:00-24:00: Recuperación parcial (+1%)
    restante = total - 16 - 16 - 20 - 8 - 12
    for i in range(max(0, restante)):
        cambio = random.gauss(0.0004, 0.002)
        precios.append(precios[-1] * (1 + cambio))

    return precios

# ============================================================
# MOTOR DE SIMULACIÓN
# ============================================================

COMISION_PCT = 0.001  # 0.10% por operación

class SimuladorDCA:
    def __init__(self, params):
        self.p = params
        self.reset()

    def reset(self):
        self.capital = self.p['capital_inicial']
        self.in_position = False
        self.entry_price = 0
        self.amount = 0
        self.dca_level = 0
        self.trailing_active = False
        self.highest_price = 0
        self.trades = []
        self.capital_history = []
        self.cooldown_ticks = 0
        self.ticks_in_trade = 0

    def _comision(self, monto_usdt):
        return monto_usdt * COMISION_PCT

    def _comprar(self, precio, capital_usar):
        fee = self._comision(capital_usar)
        capital_efectivo = capital_usar - fee
        cantidad = capital_efectivo / precio
        return cantidad, fee

    def _vender(self, precio, cantidad):
        bruto = precio * cantidad
        fee = self._comision(bruto)
        neto = bruto - fee
        return neto, fee

    def _deberia_comprar(self, precios, idx):
        """Señal simplificada: simula confluencia con momentum de precio"""
        if idx < 20:
            return False
        if self.cooldown_ticks > 0:
            self.cooldown_ticks -= 1
            return False

        # Simular RSI/momentum usando precios recientes
        ventana = precios[max(0, idx-14):idx+1]
        ganancias = sum(max(0, ventana[i] - ventana[i-1]) for i in range(1, len(ventana)))
        perdidas = sum(max(0, ventana[i-1] - ventana[i]) for i in range(1, len(ventana)))

        if perdidas == 0:
            rsi = 100
        elif ganancias == 0:
            rsi = 0
        else:
            rs = ganancias / perdidas
            rsi = 100 - (100 / (1 + rs))

        # EMA simple
        ema_corta = sum(precios[max(0, idx-10):idx+1]) / min(11, idx+1)
        ema_larga = sum(precios[max(0, idx-40):idx+1]) / min(41, idx+1)

        precio_actual = precios[idx]

        # Señal: RSI en rango de compra + precio sobre EMAs + momentum
        rsi_ok = self.p['rsi_min'] < rsi < self.p['rsi_max']
        tendencia_ok = precio_actual > ema_larga
        momentum_ok = precio_actual > precios[idx-1] if idx > 0 else True

        return rsi_ok and tendencia_ok and momentum_ok

    def simular(self, precios):
        self.reset()
        self.capital_history = [self.capital]
        total_fees = 0

        for idx in range(len(precios)):
            precio = precios[idx]

            if self.in_position:
                self.ticks_in_trade += 1
                roi = (precio - self.entry_price) / self.entry_price

                vender = False
                motivo = ""

                # 1. TIMEOUT: Salir si lleva demasiado tiempo
                max_ticks = self.p.get('max_hold_ticks', 999)
                if self.ticks_in_trade >= max_ticks and roi > -self.p['stop_loss_pct'] * 0.5:
                    vender = True
                    motivo = f"TIMEOUT ({self.ticks_in_trade} ticks, ROI:{roi*100:.2f}%)"

                # 2. TRAILING TAKE PROFIT
                if not vender and roi >= self.p['tp_activation_pct']:
                    if not self.trailing_active:
                        self.trailing_active = True
                        self.highest_price = precio
                    elif precio > self.highest_price:
                        self.highest_price = precio

                    trailing_sell = self.highest_price * (1 - self.p['trailing_pct'])
                    if precio <= trailing_sell:
                        vender = True
                        motivo = f"TRAILING (+{roi*100:.2f}%)"

                # 3. STOP LOSS
                if not vender and roi <= -self.p['stop_loss_pct']:
                    vender = True
                    motivo = f"STOP LOSS ({roi*100:.2f}%)"

                # 4. DCA (Dollar Cost Averaging)
                if not vender and not self.trailing_active:
                    dca_drops = self.p.get('dca_drops', [])
                    if self.dca_level < len(dca_drops) and roi <= dca_drops[self.dca_level]:
                        # Simular rebote check (50% probabilidad de confirmar)
                        if random.random() > 0.4:  # 60% de rebotes se confirman
                            budget = self.capital * self.p['max_exposure']
                            alloc = self.p.get('dca_allocs', [0.15, 0.20, 0.25])
                            if self.dca_level < len(alloc):
                                capital_dca = budget * alloc[self.dca_level]
                                capital_dca = min(capital_dca, self.capital * 0.95)

                                if capital_dca > 10:
                                    cantidad_dca, fee = self._comprar(precio, capital_dca)
                                    total_fees += fee

                                    old_amount = self.amount
                                    old_entry = self.entry_price
                                    self.amount += cantidad_dca
                                    self.entry_price = ((old_amount * old_entry) + (cantidad_dca * precio)) / self.amount
                                    self.capital -= capital_dca
                                    self.dca_level += 1
                                    self.trailing_active = False
                                    self.highest_price = 0

                if vender:
                    neto, fee = self._vender(precio, self.amount)
                    total_fees += fee
                    profit = neto - (self.entry_price * self.amount)

                    self.capital += neto
                    self.trades.append({
                        'entry': self.entry_price,
                        'exit': precio,
                        'roi': roi,
                        'profit': profit,
                        'dca_level': self.dca_level,
                        'ticks': self.ticks_in_trade,
                        'motivo': motivo,
                    })

                    self.in_position = False
                    self.amount = 0
                    self.entry_price = 0
                    self.dca_level = 0
                    self.trailing_active = False
                    self.highest_price = 0
                    self.ticks_in_trade = 0
                    self.cooldown_ticks = self.p.get('cooldown_after_sl', 4) if 'STOP' in motivo else self.p.get('cooldown_after_win', 2)

            else:
                # Buscar entrada
                if self._deberia_comprar(precios, idx):
                    budget = self.capital * self.p['max_exposure']
                    capital_compra = budget * self.p['base_alloc']
                    capital_compra = min(capital_compra, self.capital * 0.95)

                    if capital_compra > 10:
                        cantidad, fee = self._comprar(precio, capital_compra)
                        total_fees += fee

                        self.in_position = True
                        self.entry_price = precio
                        self.amount = cantidad
                        self.capital -= capital_compra
                        self.dca_level = 0
                        self.trailing_active = False
                        self.highest_price = 0
                        self.ticks_in_trade = 0

            # Track capital incluyendo posición abierta
            valor_total = self.capital + (self.amount * precio if self.in_position else 0)
            self.capital_history.append(valor_total)

        # Cerrar posición abierta al final
        if self.in_position:
            precio_final = precios[-1]
            roi = (precio_final - self.entry_price) / self.entry_price
            neto, fee = self._vender(precio_final, self.amount)
            total_fees += fee
            self.capital += neto
            self.trades.append({
                'entry': self.entry_price,
                'exit': precio_final,
                'roi': roi,
                'profit': neto - (self.entry_price * self.amount),
                'dca_level': self.dca_level,
                'ticks': self.ticks_in_trade,
                'motivo': 'CIERRE FORZADO (fin simulación)',
            })
            self.in_position = False
            self.amount = 0

        return {
            'capital_final': self.capital,
            'retorno_pct': (self.capital - self.p['capital_inicial']) / self.p['capital_inicial'] * 100,
            'num_trades': len(self.trades),
            'trades': self.trades,
            'total_fees': total_fees,
            'max_drawdown': self._max_drawdown(),
            'win_rate': self._win_rate(),
        }

    def _max_drawdown(self):
        if not self.capital_history:
            return 0
        peak = self.capital_history[0]
        max_dd = 0
        for v in self.capital_history:
            if v > peak:
                peak = v
            dd = (peak - v) / peak
            if dd > max_dd:
                max_dd = dd
        return max_dd * 100

    def _win_rate(self):
        if not self.trades:
            return 0
        wins = sum(1 for t in self.trades if t['profit'] > 0)
        return wins / len(self.trades) * 100


# ============================================================
# CONFIGURACIONES A PROBAR
# ============================================================

PARAMS_ACTUAL = {
    'nombre': 'ACTUAL (Estrategia Vigente)',
    'capital_inicial': 4400,
    'max_exposure': 0.60,
    'base_alloc': 0.25,
    'tp_activation_pct': 0.01,
    'trailing_pct': 0.005,
    'stop_loss_pct': 0.025,
    'dca_drops': [-0.015, -0.030, -0.045],
    'dca_allocs': [0.15, 0.25, 0.35],
    'rsi_min': 25,
    'rsi_max': 58,
    'max_hold_ticks': 999,  # Sin límite
    'cooldown_after_sl': 4,
    'cooldown_after_win': 2,
}

PARAMS_V2_AGRESIVO = {
    'nombre': 'V2 - Agresivo (Mayor posición, TP más amplio)',
    'capital_inicial': 4400,
    'max_exposure': 0.75,        # 75% exposición
    'base_alloc': 0.35,          # 35% del budget en entrada base
    'tp_activation_pct': 0.012,  # TP a 1.2%
    'trailing_pct': 0.004,       # Trail -0.4% desde pico
    'stop_loss_pct': 0.018,      # SL más ajustado -1.8%
    'dca_drops': [-0.012, -0.024],  # Solo 2 DCA, más cercanos
    'dca_allocs': [0.20, 0.30],
    'rsi_min': 30,
    'rsi_max': 65,               # RSI más permisivo
    'max_hold_ticks': 48,        # Max 12 horas
    'cooldown_after_sl': 8,      # Más cooldown post-SL
    'cooldown_after_win': 1,
}

PARAMS_V3_SCALP_DCA = {
    'nombre': 'V3 - Scalp-DCA Híbrido (Trades rápidos)',
    'capital_inicial': 4400,
    'max_exposure': 0.80,        # 80% exposición
    'base_alloc': 0.40,          # 40% entrada base
    'tp_activation_pct': 0.008,  # TP a 0.8% (más rápido)
    'trailing_pct': 0.003,       # Trail -0.3%
    'stop_loss_pct': 0.012,      # SL ajustado -1.2%
    'dca_drops': [-0.008, -0.016],  # DCA agresivo
    'dca_allocs': [0.25, 0.35],
    'rsi_min': 28,
    'rsi_max': 68,               # Muy permisivo
    'max_hold_ticks': 24,        # Max 6 horas
    'cooldown_after_sl': 6,
    'cooldown_after_win': 1,
}

PARAMS_V4_MOMENTUM = {
    'nombre': 'V4 - Momentum Rider (Dejar correr ganadores)',
    'capital_inicial': 4400,
    'max_exposure': 0.70,
    'base_alloc': 0.35,
    'tp_activation_pct': 0.015,  # TP más lejos 1.5%
    'trailing_pct': 0.007,       # Trail -0.7% (más holgado)
    'stop_loss_pct': 0.015,      # SL ajustado -1.5%
    'dca_drops': [-0.010, -0.020, -0.030],
    'dca_allocs': [0.15, 0.20, 0.30],
    'rsi_min': 30,
    'rsi_max': 62,
    'max_hold_ticks': 40,        # Max 10 horas
    'cooldown_after_sl': 6,
    'cooldown_after_win': 1,
}

PARAMS_V5_BALANCED = {
    'nombre': 'V5 - Balanced Optimized',
    'capital_inicial': 4400,
    'max_exposure': 0.75,
    'base_alloc': 0.35,
    'tp_activation_pct': 0.010,  # TP 1.0%
    'trailing_pct': 0.004,       # Trail -0.4%
    'stop_loss_pct': 0.015,      # SL -1.5%
    'dca_drops': [-0.010, -0.020],
    'dca_allocs': [0.20, 0.30],
    'rsi_min': 30,
    'rsi_max': 65,
    'max_hold_ticks': 32,        # Max 8 horas
    'cooldown_after_sl': 6,
    'cooldown_after_win': 1,
}

PARAMS_V6_QUICK_SNIPER = {
    'nombre': 'V6 - Quick Sniper (Muchos trades pequeños)',
    'capital_inicial': 4400,
    'max_exposure': 0.85,
    'base_alloc': 0.45,          # Gran posición base
    'tp_activation_pct': 0.007,  # TP rápido 0.7%
    'trailing_pct': 0.003,       # Trail -0.3%
    'stop_loss_pct': 0.010,      # SL ultra-ajustado -1.0%
    'dca_drops': [-0.007],       # Solo 1 DCA
    'dca_allocs': [0.35],
    'rsi_min': 30,
    'rsi_max': 70,               # Muy permisivo
    'max_hold_ticks': 16,        # Max 4 horas
    'cooldown_after_sl': 4,
    'cooldown_after_win': 1,
}


# ============================================================
# EJECUCIÓN DE SIMULACIONES
# ============================================================

def ejecutar_simulacion_completa():
    random.seed(42)  # Reproducibilidad

    escenarios = {
        'Alcista':            lambda: generar_precios_tendencia_alcista(),
        'Bajista':            lambda: generar_precios_tendencia_bajista(),
        'Lateral':            lambda: generar_precios_lateral(),
        'Crash+Rebote':       lambda: generar_precios_crash_y_rebote(),
        'Pump&Dump':          lambda: generar_precios_pump_and_dump(),
        'Vol. Extrema':       lambda: generar_precios_volatilidad_extrema(),
        'Escalera Alcista':   lambda: generar_precios_escalera_alcista(),
        'Patrón Real BTC':    lambda: generar_precios_real_btc_marzo(),
    }

    configs = [
        PARAMS_ACTUAL,
        PARAMS_V2_AGRESIVO,
        PARAMS_V3_SCALP_DCA,
        PARAMS_V4_MOMENTUM,
        PARAMS_V5_BALANCED,
        PARAMS_V6_QUICK_SNIPER,
    ]

    NUM_SIMULACIONES = 50  # Promedio sobre múltiples runs por escenario

    print("=" * 120)
    print("SIMULADOR DE BACKTESTING - OPTIMIZACIÓN DE ESTRATEGIA DCA")
    print(f"Capital Inicial: 4,400 USDT | Comisiones: 0.10% por operación | Objetivo: +2% diario")
    print("=" * 120)

    # Resultados globales por config
    resultados_globales = {c['nombre']: {'retornos': [], 'trades': [], 'winrates': [], 'drawdowns': [], 'fees': []} for c in configs}

    for nombre_esc, generador in escenarios.items():
        print(f"\n{'─' * 120}")
        print(f"📊 ESCENARIO: {nombre_esc}")
        print(f"{'─' * 120}")
        print(f"{'Estrategia':<45} {'Retorno%':>9} {'Trades':>7} {'Win%':>6} {'MaxDD%':>7} {'Fees':>8} {'P/L USDT':>10} {'Meta 2%':>8}")
        print(f"{'─' * 45} {'─'*9} {'─'*7} {'─'*6} {'─'*7} {'─'*8} {'─'*10} {'─'*8}")

        for config in configs:
            retornos = []
            total_trades = []
            winrates = []
            drawdowns = []
            fees_list = []

            for sim in range(NUM_SIMULACIONES):
                random.seed(42 + sim * 137 + hash(nombre_esc) % 1000)
                precios = generador()

                simulador = SimuladorDCA(config)
                resultado = simulador.simular(precios)

                retornos.append(resultado['retorno_pct'])
                total_trades.append(resultado['num_trades'])
                winrates.append(resultado['win_rate'])
                drawdowns.append(resultado['max_drawdown'])
                fees_list.append(resultado['total_fees'])

            avg_ret = sum(retornos) / len(retornos)
            avg_trades = sum(total_trades) / len(total_trades)
            avg_wr = sum(winrates) / len(winrates) if winrates else 0
            avg_dd = sum(drawdowns) / len(drawdowns)
            avg_fees = sum(fees_list) / len(fees_list)
            avg_pl = avg_ret * config['capital_inicial'] / 100
            meta = "✅" if avg_ret >= 2.0 else "⚠️" if avg_ret >= 1.0 else "❌"

            resultados_globales[config['nombre']]['retornos'].append(avg_ret)
            resultados_globales[config['nombre']]['trades'].append(avg_trades)
            resultados_globales[config['nombre']]['winrates'].append(avg_wr)
            resultados_globales[config['nombre']]['drawdowns'].append(avg_dd)
            resultados_globales[config['nombre']]['fees'].append(avg_fees)

            nombre_corto = config['nombre'][:44]
            print(f"{nombre_corto:<45} {avg_ret:>+8.2f}% {avg_trades:>6.1f} {avg_wr:>5.1f}% {avg_dd:>6.2f}% {avg_fees:>7.2f} {avg_pl:>+9.2f} {meta:>6}")

    # RESUMEN GLOBAL
    print(f"\n{'=' * 120}")
    print("🏆 RESUMEN GLOBAL (PROMEDIO DE TODOS LOS ESCENARIOS)")
    print(f"{'=' * 120}")
    print(f"{'Estrategia':<45} {'Ret.Prom%':>9} {'Trades/d':>9} {'Win%':>6} {'MaxDD%':>7} {'Fees/d':>8} {'P/L USDT':>10} {'Sharpe':>7}")
    print(f"{'─' * 45} {'─'*9} {'─'*9} {'─'*6} {'─'*7} {'─'*8} {'─'*10} {'─'*7}")

    ranking = []
    for config in configs:
        datos = resultados_globales[config['nombre']]
        avg_ret = sum(datos['retornos']) / len(datos['retornos'])
        avg_trades = sum(datos['trades']) / len(datos['trades'])
        avg_wr = sum(datos['winrates']) / len(datos['winrates'])
        avg_dd = sum(datos['drawdowns']) / len(datos['drawdowns'])
        avg_fees = sum(datos['fees']) / len(datos['fees'])
        avg_pl = avg_ret * config['capital_inicial'] / 100

        # Pseudo-Sharpe: retorno / volatilidad de retornos
        if len(datos['retornos']) > 1:
            mean_r = sum(datos['retornos']) / len(datos['retornos'])
            var_r = sum((r - mean_r)**2 for r in datos['retornos']) / len(datos['retornos'])
            std_r = var_r ** 0.5
            sharpe = mean_r / std_r if std_r > 0 else 0
        else:
            sharpe = 0

        nombre_corto = config['nombre'][:44]
        print(f"{nombre_corto:<45} {avg_ret:>+8.2f}% {avg_trades:>8.1f} {avg_wr:>5.1f}% {avg_dd:>6.2f}% {avg_fees:>7.2f} {avg_pl:>+9.2f} {sharpe:>6.2f}")
        ranking.append((config['nombre'], avg_ret, avg_dd, sharpe, config))

    # Ordenar por mejor combinación retorno/riesgo
    ranking.sort(key=lambda x: x[3], reverse=True)

    print(f"\n{'=' * 120}")
    print("🎯 RANKING FINAL (por Sharpe Ratio - mejor retorno ajustado por riesgo)")
    print(f"{'=' * 120}")
    for i, (nombre, ret, dd, sharpe, config) in enumerate(ranking):
        medalla = ["🥇", "🥈", "🥉", "4️⃣ ", "5️⃣ ", "6️⃣ "][i]
        print(f"{medalla} {nombre:<50} Ret:{ret:>+6.2f}% | DD:{dd:>5.2f}% | Sharpe:{sharpe:>5.2f}")

    # Mostrar parámetros del ganador
    ganador = ranking[0]
    print(f"\n{'=' * 120}")
    print(f"⭐ PARÁMETROS RECOMENDADOS: {ganador[0]}")
    print(f"{'=' * 120}")
    config_ganador = ganador[4]
    for k, v in config_ganador.items():
        if k not in ('nombre', 'capital_inicial'):
            print(f"  {k:<25} = {v}")

    print(f"\n{'=' * 120}")
    print("📋 ANÁLISIS DETALLADO DEL GANADOR - Último run por escenario")
    print(f"{'=' * 120}")

    for nombre_esc, generador in escenarios.items():
        random.seed(42)
        precios = generador()
        simulador = SimuladorDCA(config_ganador)
        resultado = simulador.simular(precios)

        print(f"\n  📊 {nombre_esc}: {resultado['retorno_pct']:+.2f}% | {resultado['num_trades']} trades | WR:{resultado['win_rate']:.0f}%")
        for t in resultado['trades'][:10]:
            print(f"     Entry:{t['entry']:.0f} → Exit:{t['exit']:.0f} | ROI:{t['roi']*100:+.2f}% | DCA:{t['dca_level']} | {t['motivo']}")


if __name__ == '__main__':
    ejecutar_simulacion_completa()
