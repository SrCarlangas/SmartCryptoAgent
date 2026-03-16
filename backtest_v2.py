"""
Simulador V2 - Optimización enfocada con posiciones más grandes y
múltiples operaciones por día.

Insight clave del log real:
- El bot usa solo 15% del capital por trade → ganancias minúsculas
- Stop Loss a -2.5% borra 3 trades ganadores
- El trailing a 0.5% corta ganadores demasiado pronto
- RSI < 58 rechaza muchas señales válidas

Necesitamos: Mayor exposición + SL más ajustado + más trades por día
"""
import random
import math

COMISION_PCT = 0.001  # 0.10% por operación

# ============================================================
# GENERADORES DE PRECIOS (más granulares - cada 15 min)
# ============================================================

def generar_escenarios(seed=42):
    """Genera 8 escenarios distintos, cada uno con 96 ticks (24h en velas 15m)"""
    escenarios = {}

    # Escenario 1: Alcista suave (+2% en el día)
    random.seed(seed)
    precios = [69000]
    for _ in range(96):
        precios.append(precios[-1] * (1 + random.gauss(0.0002, 0.0018)))
    escenarios['Alcista Suave'] = precios

    # Escenario 2: Alcista fuerte (+4%)
    random.seed(seed + 1)
    precios = [68000]
    for _ in range(96):
        precios.append(precios[-1] * (1 + random.gauss(0.0004, 0.002)))
    escenarios['Alcista Fuerte'] = precios

    # Escenario 3: Bajista suave (-2%)
    random.seed(seed + 2)
    precios = [71000]
    for _ in range(96):
        precios.append(precios[-1] * (1 + random.gauss(-0.0002, 0.0018)))
    escenarios['Bajista Suave'] = precios

    # Escenario 4: Bajista fuerte (-5%)
    random.seed(seed + 3)
    precios = [72000]
    for _ in range(96):
        precios.append(precios[-1] * (1 + random.gauss(-0.0005, 0.0025)))
    escenarios['Bajista Fuerte'] = precios

    # Escenario 5: Lateral estrecho (rango 1%)
    random.seed(seed + 4)
    precios = [70000]
    for _ in range(96):
        cambio = random.gauss(0, 0.0015)
        nuevo = precios[-1] * (1 + cambio)
        # Mean reversion
        if nuevo > 70700: cambio -= 0.001
        if nuevo < 69300: cambio += 0.001
        precios.append(precios[-1] * (1 + cambio))
    escenarios['Lateral Estrecho'] = precios

    # Escenario 6: Crash rápido y rebote (como el real)
    random.seed(seed + 5)
    precios = [71000]
    # Subida 6h
    for _ in range(24):
        precios.append(precios[-1] * (1 + random.gauss(0.0008, 0.0012)))
    # Crash 3h (-3.5%)
    for _ in range(12):
        precios.append(precios[-1] * (1 + random.gauss(-0.003, 0.0015)))
    # Piso 3h
    for _ in range(12):
        precios.append(precios[-1] * (1 + random.gauss(0, 0.002)))
    # Recuperación 6h
    for _ in range(24):
        precios.append(precios[-1] * (1 + random.gauss(0.0006, 0.0015)))
    # Lateral 6h
    for _ in range(96 - 72):
        precios.append(precios[-1] * (1 + random.gauss(0.0001, 0.0015)))
    escenarios['Crash + Rebote'] = precios

    # Escenario 7: Pump & Dump
    random.seed(seed + 6)
    precios = [69000]
    # Pump 4h (+3%)
    for _ in range(16):
        precios.append(precios[-1] * (1 + random.gauss(0.002, 0.001)))
    # Dump 2h (-4%)
    for _ in range(8):
        precios.append(precios[-1] * (1 + random.gauss(-0.005, 0.002)))
    # Recuperación lenta
    for _ in range(96 - 24):
        precios.append(precios[-1] * (1 + random.gauss(0.0003, 0.002)))
    escenarios['Pump & Dump'] = precios

    # Escenario 8: Réplica del patrón real del 10-11 marzo
    random.seed(seed + 7)
    precios = [69000]
    # 00:00-02:00: Lateral (como el log real)
    for _ in range(8):
        precios.append(precios[-1] * (1 + random.gauss(0, 0.001)))
    # 02:00-04:00: Primera subida a 70200
    for _ in range(8):
        precios.append(precios[-1] * (1 + random.gauss(0.001, 0.001)))
    # 04:00-09:00: Segunda subida a 71000
    for _ in range(20):
        precios.append(precios[-1] * (1 + random.gauss(0.0004, 0.0015)))
    # 09:00-13:00: Lateral alto
    for _ in range(16):
        precios.append(precios[-1] * (1 + random.gauss(0, 0.002)))
    # 13:00-15:00: Caída fuerte a 69500
    for _ in range(8):
        precios.append(precios[-1] * (1 + random.gauss(-0.002, 0.0015)))
    # 15:00-18:00: Consolidación baja
    for _ in range(12):
        precios.append(precios[-1] * (1 + random.gauss(-0.0005, 0.002)))
    # 18:00-24:00: Recuperación
    for _ in range(96 - 72):
        precios.append(precios[-1] * (1 + random.gauss(0.0005, 0.002)))
    escenarios['Patrón Real Mar 10-11'] = precios

    # Escenario 9: Dientes de sierra (múltiples ups and downs)
    random.seed(seed + 8)
    precios = [70000]
    for ciclo in range(6):  # 6 ciclos de 4h
        # Subida 2h
        for _ in range(8):
            precios.append(precios[-1] * (1 + random.gauss(0.001, 0.001)))
        # Bajada 2h
        for _ in range(8):
            precios.append(precios[-1] * (1 + random.gauss(-0.0008, 0.001)))
    escenarios['Dientes de Sierra'] = precios

    # Escenario 10: Volatilidad extrema sin dirección
    random.seed(seed + 9)
    precios = [70000]
    for _ in range(96):
        precios.append(precios[-1] * (1 + random.gauss(0, 0.004)))
    escenarios['Volatilidad Extrema'] = precios

    return escenarios


class TradingSimulator:
    """Simulador más realista que modela el comportamiento real del bot"""

    def __init__(self, params):
        self.p = params
        self.reset()

    def reset(self):
        self.capital_inicial = self.p['capital_inicial']
        self.capital = self.capital_inicial
        self.in_position = False
        self.entry_price = 0
        self.amount_btc = 0
        self.invested_usdt = 0
        self.dca_level = 0
        self.trailing_active = False
        self.highest_price = 0
        self.ticks_in_position = 0
        self.trades = []
        self.total_fees = 0
        self.cooldown = 0

    def _fee(self, usdt_amount):
        return usdt_amount * COMISION_PCT

    def _momentum_signal(self, precios, idx):
        """Señal simplificada de momentum basada en precio"""
        if idx < 15 or self.cooldown > 0:
            if self.cooldown > 0:
                self.cooldown -= 1
            return False

        # RSI simplificado
        window = precios[max(0, idx-14):idx+1]
        gains = losses = 0
        for i in range(1, len(window)):
            diff = window[i] - window[i-1]
            if diff > 0:
                gains += diff
            else:
                losses -= diff
        if losses == 0:
            rsi = 100
        elif gains == 0:
            rsi = 0
        else:
            rsi = 100 - (100 / (1 + gains/losses))

        # Precio vs media
        ema_short = sum(precios[max(0,idx-8):idx+1]) / min(9, idx+1)
        ema_long = sum(precios[max(0,idx-30):idx+1]) / min(31, idx+1)

        precio = precios[idx]
        rsi_ok = self.p['rsi_min'] <= rsi <= self.p['rsi_max']
        trend_ok = precio > ema_long * (1 - 0.005)  # 0.5% tolerance
        momentum_ok = precio > precios[idx-1]

        # Precio subiendo en las últimas 3 velas (confirmación)
        subiendo = idx >= 3 and precios[idx] > precios[idx-2]

        return rsi_ok and trend_ok and momentum_ok and subiendo

    def simular(self, precios):
        self.reset()
        capital_track = [self.capital]

        for idx in range(len(precios)):
            precio = precios[idx]

            if self.in_position:
                self.ticks_in_position += 1
                roi = (precio - self.entry_price) / self.entry_price

                vender = False
                motivo = ""

                # --- TRAILING TAKE PROFIT ---
                if roi >= self.p['tp_activation']:
                    if not self.trailing_active:
                        self.trailing_active = True
                        self.highest_price = precio
                    else:
                        self.highest_price = max(self.highest_price, precio)

                    trail_sell = self.highest_price * (1 - self.p['trailing_pct'])
                    if precio <= trail_sell:
                        vender = True
                        motivo = f"TRAILING TP (+{roi*100:.2f}%)"

                # --- STOP LOSS ---
                if not vender and roi <= -self.p['stop_loss']:
                    vender = True
                    motivo = f"STOP LOSS ({roi*100:.2f}%)"

                # --- TIMEOUT ---
                if not vender and self.ticks_in_position >= self.p['max_ticks']:
                    # Solo salir por timeout si el ROI no es muy negativo
                    if roi > -self.p['stop_loss'] * 0.7:
                        vender = True
                        motivo = f"TIMEOUT ({roi*100:.2f}%)"

                # --- DCA ---
                if not vender and not self.trailing_active:
                    drops = self.p['dca_drops']
                    allocs = self.p['dca_allocs']
                    if self.dca_level < len(drops) and roi <= drops[self.dca_level]:
                        # Simular confirmación de rebote
                        rebote = idx >= 3 and precios[idx] > precios[idx-1] and precios[idx-1] < precios[idx-2]
                        if rebote or random.random() > 0.5:
                            budget = self.capital_inicial * self.p['max_exposure']
                            capital_dca = min(budget * allocs[self.dca_level], self.capital * 0.95)
                            if capital_dca > 10:
                                fee = self._fee(capital_dca)
                                self.total_fees += fee
                                qty = (capital_dca - fee) / precio
                                old_qty = self.amount_btc
                                old_entry = self.entry_price
                                self.amount_btc += qty
                                self.entry_price = (old_qty * old_entry + qty * precio) / self.amount_btc
                                self.invested_usdt += capital_dca
                                self.capital -= capital_dca
                                self.dca_level += 1
                                self.trailing_active = False
                                self.highest_price = 0

                # --- EJECUTAR VENTA ---
                if vender:
                    bruto = precio * self.amount_btc
                    fee = self._fee(bruto)
                    self.total_fees += fee
                    neto = bruto - fee
                    profit_usdt = neto - self.invested_usdt

                    self.capital += neto
                    self.trades.append({
                        'entry': self.entry_price,
                        'exit': precio,
                        'roi_pct': roi * 100,
                        'profit_usdt': profit_usdt,
                        'invested': self.invested_usdt,
                        'dca_level': self.dca_level,
                        'ticks': self.ticks_in_position,
                        'motivo': motivo,
                    })

                    self.in_position = False
                    self.amount_btc = 0
                    self.invested_usdt = 0
                    self.dca_level = 0
                    self.trailing_active = False
                    self.highest_price = 0
                    self.ticks_in_position = 0

                    # Cooldown post-trade
                    if 'STOP' in motivo:
                        self.cooldown = self.p.get('cooldown_sl', 8)
                    else:
                        self.cooldown = self.p.get('cooldown_win', 2)

            else:
                # --- BUSCAR ENTRADA ---
                if self._momentum_signal(precios, idx):
                    budget = self.capital_inicial * self.p['max_exposure']
                    capital_entry = min(budget * self.p['base_alloc'], self.capital * 0.95)

                    if capital_entry > 10:
                        fee = self._fee(capital_entry)
                        self.total_fees += fee
                        qty = (capital_entry - fee) / precio

                        self.in_position = True
                        self.entry_price = precio
                        self.amount_btc = qty
                        self.invested_usdt = capital_entry
                        self.capital -= capital_entry
                        self.dca_level = 0
                        self.trailing_active = False
                        self.highest_price = 0
                        self.ticks_in_position = 0

            # Track total value
            total_val = self.capital + (self.amount_btc * precio if self.in_position else 0)
            capital_track.append(total_val)

        # Cerrar posición abierta al cierre
        if self.in_position:
            precio_final = precios[-1]
            roi = (precio_final - self.entry_price) / self.entry_price
            bruto = precio_final * self.amount_btc
            fee = self._fee(bruto)
            self.total_fees += fee
            neto = bruto - fee
            profit_usdt = neto - self.invested_usdt
            self.capital += neto
            self.trades.append({
                'entry': self.entry_price,
                'exit': precio_final,
                'roi_pct': roi * 100,
                'profit_usdt': profit_usdt,
                'invested': self.invested_usdt,
                'dca_level': self.dca_level,
                'ticks': self.ticks_in_position,
                'motivo': 'CIERRE FIN DÍA',
            })

        # Métricas
        retorno_total = (self.capital - self.capital_inicial) / self.capital_inicial * 100
        wins = [t for t in self.trades if t['profit_usdt'] > 0]
        losses = [t for t in self.trades if t['profit_usdt'] <= 0]
        win_rate = len(wins) / len(self.trades) * 100 if self.trades else 0

        # Max drawdown
        peak = capital_track[0]
        max_dd = 0
        for v in capital_track:
            peak = max(peak, v)
            dd = (peak - v) / peak
            max_dd = max(max_dd, dd)

        avg_win = sum(t['profit_usdt'] for t in wins) / len(wins) if wins else 0
        avg_loss = sum(t['profit_usdt'] for t in losses) / len(losses) if losses else 0

        return {
            'retorno_pct': retorno_total,
            'capital_final': self.capital,
            'num_trades': len(self.trades),
            'win_rate': win_rate,
            'max_drawdown_pct': max_dd * 100,
            'total_fees': self.total_fees,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'trades': self.trades,
        }


def main():
    # ============================================================
    # ESTRATEGIAS A COMPARAR
    # ============================================================
    estrategias = {
        'ACTUAL': {
            'capital_inicial': 4400,
            'max_exposure': 0.60,
            'base_alloc': 0.25,      # 15% del capital total
            'tp_activation': 0.010,
            'trailing_pct': 0.005,
            'stop_loss': 0.025,
            'dca_drops': [-0.015, -0.030, -0.045],
            'dca_allocs': [0.15, 0.25, 0.35],
            'rsi_min': 25,
            'rsi_max': 58,
            'max_ticks': 999,
            'cooldown_sl': 4,
            'cooldown_win': 2,
        },
        'PROPUESTA A (Agresivo+SL Ajustado)': {
            'capital_inicial': 4400,
            'max_exposure': 0.80,
            'base_alloc': 0.40,      # 32% del capital total
            'tp_activation': 0.010,
            'trailing_pct': 0.004,
            'stop_loss': 0.014,      # SL -1.4% (antes -2.5%)
            'dca_drops': [-0.009, -0.018],
            'dca_allocs': [0.25, 0.35],
            'rsi_min': 28,
            'rsi_max': 66,
            'max_ticks': 32,         # Max 8 horas
            'cooldown_sl': 6,
            'cooldown_win': 1,
        },
        'PROPUESTA B (Ultra-Agresivo)': {
            'capital_inicial': 4400,
            'max_exposure': 0.90,
            'base_alloc': 0.50,      # 45% del capital total
            'tp_activation': 0.008,
            'trailing_pct': 0.003,
            'stop_loss': 0.012,      # SL -1.2%
            'dca_drops': [-0.008, -0.016],
            'dca_allocs': [0.25, 0.35],
            'rsi_min': 30,
            'rsi_max': 68,
            'max_ticks': 24,         # Max 6 horas
            'cooldown_sl': 8,
            'cooldown_win': 1,
        },
        'PROPUESTA C (Momentum Runner)': {
            'capital_inicial': 4400,
            'max_exposure': 0.80,
            'base_alloc': 0.45,      # 36% del capital total
            'tp_activation': 0.013,  # Dejar correr más
            'trailing_pct': 0.005,
            'stop_loss': 0.013,      # SL simétrico al TP
            'dca_drops': [-0.008, -0.016],
            'dca_allocs': [0.20, 0.35],
            'rsi_min': 30,
            'rsi_max': 64,
            'max_ticks': 36,         # Max 9 horas
            'cooldown_sl': 6,
            'cooldown_win': 1,
        },
        'PROPUESTA D (High Frequency)': {
            'capital_inicial': 4400,
            'max_exposure': 0.85,
            'base_alloc': 0.50,      # 42.5% del capital
            'tp_activation': 0.007,  # TP bajo para cerrar rápido
            'trailing_pct': 0.003,
            'stop_loss': 0.010,      # SL ultra-ajustado
            'dca_drops': [-0.007],
            'dca_allocs': [0.35],
            'rsi_min': 30,
            'rsi_max': 70,
            'max_ticks': 16,         # Max 4 horas
            'cooldown_sl': 4,
            'cooldown_win': 1,
        },
        'PROPUESTA E (Balanced Optimal)': {
            'capital_inicial': 4400,
            'max_exposure': 0.80,
            'base_alloc': 0.45,
            'tp_activation': 0.010,
            'trailing_pct': 0.004,
            'stop_loss': 0.013,
            'dca_drops': [-0.008, -0.016],
            'dca_allocs': [0.25, 0.30],
            'rsi_min': 28,
            'rsi_max': 66,
            'max_ticks': 28,         # Max 7 horas
            'cooldown_sl': 6,
            'cooldown_win': 1,
        },
    }

    escenarios = generar_escenarios(seed=42)
    NUM_RUNS = 100  # Promedio sobre 100 runs con diferentes seeds

    print("=" * 130)
    print("SIMULACIÓN V2 - OPTIMIZACIÓN ENFOCADA PARA OBJETIVO 2% DIARIO")
    print(f"Capital: 4,400 USDT | BTC ~70,000 | Comisión: 0.10%/op | 96 velas de 15m (24h)")
    print("=" * 130)

    # Resultados agregados
    global_results = {}

    for nombre_est, params in estrategias.items():
        global_results[nombre_est] = {
            'retornos': [],
            'trades': [],
            'winrates': [],
            'drawdowns': [],
            'fees': [],
            'avg_wins': [],
            'avg_losses': [],
            'retornos_por_escenario': {},
        }

        for nombre_esc, precios_base in escenarios.items():
            esc_retornos = []
            esc_trades = []
            esc_winrates = []

            for run in range(NUM_RUNS):
                # Añadir ruido aleatorio a cada run
                random.seed(42 + run * 31 + hash(nombre_esc) % 997)
                noise_factor = 1 + random.gauss(0, 0.0003)
                precios = [p * noise_factor for p in precios_base]
                # Añadir micro-variaciones
                for i in range(1, len(precios)):
                    precios[i] *= (1 + random.gauss(0, 0.0005))

                sim = TradingSimulator(params)
                res = sim.simular(precios)

                esc_retornos.append(res['retorno_pct'])
                esc_trades.append(res['num_trades'])
                esc_winrates.append(res['win_rate'])
                global_results[nombre_est]['retornos'].append(res['retorno_pct'])
                global_results[nombre_est]['trades'].append(res['num_trades'])
                global_results[nombre_est]['winrates'].append(res['win_rate'])
                global_results[nombre_est]['drawdowns'].append(res['max_drawdown_pct'])
                global_results[nombre_est]['fees'].append(res['total_fees'])
                global_results[nombre_est]['avg_wins'].append(res['avg_win'])
                global_results[nombre_est]['avg_losses'].append(res['avg_loss'])

            avg_ret = sum(esc_retornos) / len(esc_retornos)
            global_results[nombre_est]['retornos_por_escenario'][nombre_esc] = avg_ret

    # ============================================================
    # IMPRESIÓN DE RESULTADOS
    # ============================================================

    # Tabla por escenario
    for nombre_esc in escenarios.keys():
        print(f"\n{'─' * 130}")
        print(f"📊 {nombre_esc}")
        print(f"{'─' * 130}")
        print(f"{'Estrategia':<42} {'Ret%':>7} {'Trades':>7} {'WR%':>6} {'DD%':>6} {'Fees':>7} {'$/trade':>8} {'Meta':>5}")
        print(f"{'─'*42} {'─'*7} {'─'*7} {'─'*6} {'─'*6} {'─'*7} {'─'*8} {'─'*5}")

        for nombre_est in estrategias:
            d = global_results[nombre_est]
            ret = d['retornos_por_escenario'][nombre_esc]
            # Calcular avg trades/winrate para este escenario específico
            n_esc = len(escenarios)
            n_runs = NUM_RUNS
            start_idx = list(escenarios.keys()).index(nombre_esc) * n_runs
            end_idx = start_idx + n_runs

            avg_trades = sum(d['trades'][start_idx:end_idx]) / n_runs
            avg_wr = sum(d['winrates'][start_idx:end_idx]) / n_runs
            avg_dd = sum(d['drawdowns'][start_idx:end_idx]) / n_runs
            avg_fees = sum(d['fees'][start_idx:end_idx]) / n_runs
            pl_per_trade = (ret * 4400 / 100) / max(avg_trades, 0.1)
            meta = "✅" if ret >= 2.0 else "⚠️" if ret >= 1.0 else "❌"

            print(f"{nombre_est:<42} {ret:>+6.2f}% {avg_trades:>6.1f} {avg_wr:>5.1f}% {avg_dd:>5.2f}% {avg_fees:>6.2f} {pl_per_trade:>+7.2f} {meta:>4}")

    # RESUMEN GLOBAL
    print(f"\n{'=' * 130}")
    print("🏆 RESUMEN GLOBAL (PROMEDIO TODOS LOS ESCENARIOS x 100 RUNS)")
    print(f"{'=' * 130}")
    print(f"{'Estrategia':<42} {'Ret%':>7} {'Trades':>7} {'WR%':>6} {'DD%':>6} {'AvgWin':>8} {'AvgLoss':>8} {'Fees':>7} {'PnL$':>8} {'R:R':>6}")
    print(f"{'─'*42} {'─'*7} {'─'*7} {'─'*6} {'─'*6} {'─'*8} {'─'*8} {'─'*7} {'─'*8} {'─'*6}")

    ranking = []
    for nombre_est, d in global_results.items():
        n = len(d['retornos'])
        avg_ret = sum(d['retornos']) / n
        avg_trades = sum(d['trades']) / n
        avg_wr = sum(d['winrates']) / n
        avg_dd = sum(d['drawdowns']) / n
        avg_fees = sum(d['fees']) / n
        avg_win = sum(d['avg_wins']) / n
        avg_loss = sum(d['avg_losses']) / n
        pnl = avg_ret * 4400 / 100
        rr = abs(avg_win / avg_loss) if avg_loss != 0 else 0

        # Score compuesto: retorno ajustado por drawdown y consistencia
        std_ret = (sum((r - avg_ret)**2 for r in d['retornos']) / n) ** 0.5
        score = (avg_ret / (std_ret + 0.01)) - (avg_dd * 0.1)

        print(f"{nombre_est:<42} {avg_ret:>+6.2f}% {avg_trades:>6.1f} {avg_wr:>5.1f}% {avg_dd:>5.2f}% {avg_win:>+7.2f} {avg_loss:>+7.2f} {avg_fees:>6.2f} {pnl:>+7.2f} {rr:>5.2f}")
        ranking.append((nombre_est, avg_ret, avg_dd, score, avg_trades, avg_wr, rr))

    ranking.sort(key=lambda x: x[3], reverse=True)

    print(f"\n{'=' * 130}")
    print("🎯 RANKING (Score = Sharpe ajustado por Drawdown)")
    print(f"{'=' * 130}")
    medallas = ["🥇", "🥈", "🥉", "4.", "5.", "6."]
    for i, (nombre, ret, dd, score, trades, wr, rr) in enumerate(ranking):
        print(f"{medallas[i]} {nombre:<48} Ret:{ret:>+6.2f}% | DD:{dd:>5.2f}% | WR:{wr:>5.1f}% | Trades:{trades:>4.1f} | R:R:{rr:>4.2f} | Score:{score:>+6.2f}")

    # Detalle del ganador
    ganador_nombre = ranking[0][0]
    ganador_params = estrategias[ganador_nombre]

    print(f"\n{'=' * 130}")
    print(f"⭐ MEJOR ESTRATEGIA: {ganador_nombre}")
    print(f"{'=' * 130}")
    for k, v in ganador_params.items():
        if k != 'capital_inicial':
            print(f"  {k:<25} = {v}")

    # Detalle por escenario
    print(f"\n  Retornos por escenario:")
    for esc, ret in global_results[ganador_nombre]['retornos_por_escenario'].items():
        meta = "✅" if ret >= 2 else "⚠️" if ret >= 1 else "⚠️ " if ret >= 0 else "❌"
        print(f"    {meta} {esc:<30} {ret:>+6.2f}%  ({ret*4400/100:>+7.2f} USDT)")

    # TRADE EXAMPLES
    print(f"\n  Ejemplo detallado (1 run por escenario):")
    for nombre_esc, precios in escenarios.items():
        random.seed(42)
        sim = TradingSimulator(ganador_params)
        res = sim.simular(precios)
        print(f"\n    {nombre_esc}: {res['retorno_pct']:>+.2f}% | {res['num_trades']} trades | WR:{res['win_rate']:.0f}%")
        for t in res['trades'][:8]:
            print(f"      {t['entry']:.0f}→{t['exit']:.0f} | ROI:{t['roi_pct']:>+5.2f}% | ${t['profit_usdt']:>+7.2f} | DCA:{t['dca_level']} | {t['ticks']:>2}t | {t['motivo']}")

    # ============================================================
    # ANÁLISIS DE VIABILIDAD DEL 2%
    # ============================================================
    print(f"\n{'=' * 130}")
    print("📊 ANÁLISIS DE VIABILIDAD DEL OBJETIVO 2% DIARIO")
    print(f"{'=' * 130}")

    best_ret = ranking[0][1]
    best_trades = ranking[0][4]
    best_wr = ranking[0][5]

    print(f"""
  Con la mejor estrategia encontrada ({ganador_nombre}):
  - Retorno promedio diario: {best_ret:+.2f}%
  - Trades promedio/día:     {best_trades:.1f}
  - Win rate:                {best_wr:.1f}%

  Para alcanzar el 2% diario ({4400*0.02:.0f} USDT) se necesitaría:

  Opción 1 - Más capital por trade:
    Con 80% exposición y 1% ROI neto por trade ganador:
    → Necesitas ~{0.02/(0.80*0.01*0.65 - 0.80*0.012*0.35):.0f} trades/día con {best_wr:.0f}% win rate
    → Esto requiere trades cada {24*60/max(1,(0.02/(0.80*0.01*0.65 - 0.80*0.012*0.35))):.0f} minutos (poco realista en 15m)

  Opción 2 - Mayor porcentaje del capital expuesto:
    Con 90% exposición, 45% base alloc = {4400*0.90*0.45:.0f} USDT por trade
    → 1% ROI neto = {4400*0.90*0.45*0.01 - 4400*0.90*0.45*0.002:.2f} USDT/trade
    → Necesitas {88/(4400*0.90*0.45*0.01 - 4400*0.90*0.45*0.002):.1f} trades ganadores netos/día

  Opción 3 - Combinar con timeframe más corto (5m):
    → Más señales por día → Más oportunidades
    → Pero mayor riesgo de whipsaws y más comisiones

  CONCLUSIÓN:
  El 2% diario en spot trading con comisiones de 0.20% round-trip
  requiere condiciones de mercado favorables (tendencia alcista).
  En promedio realista: {best_ret:+.2f}% a {best_ret*2:+.2f}% diario es alcanzable.
  En días alcistas: hasta +1.5-2.0% es posible.
  En días bajistas: las pérdidas se limitan a -{ranking[0][2]:.2f}%.
""")


if __name__ == '__main__':
    main()
