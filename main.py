import time
from modules.binance_api import BinanceConnector
from modules.sentiment import NewsAnalyzer
from modules.strategy import EstrategiaSmartDCA
from modules.risk import RiskManager
from modules.utils import cargar_estado, guardar_estado
from modules.logger import logger

# --- CONFIGURACIÓN SMART DCA 15m ---
SYMBOL = 'BTC/USDT'
TIMEFRAME = '15m'          # Timeframe principal
TIMEFRAME_TREND = '1h'     # Timeframe macro
PAUSA = 30                 # Segundos entre ciclos

# Gestión de Salida
TAKE_PROFIT_PCT = 0.015        # Meta: 1.5% Neto sobre precio promedio
STOP_LOSS_GLOBAL_PCT = 0.08    # -8.0% Stop Loss de emergencia global
DCA_NIVEL_1_DROP = 0.025       # -2.5% para activar DCA 1
DCA_NIVEL_2_DROP = 0.05        # -5.0% para activar DCA 2

# Sin timeouts: posiciones Swing pueden durar horas/días o cerrar en base al rebote
COOLDOWN_AFTER_SL = 30         # 15 minutos (30 * 30s) de enfriamiento tras SL crítico
COOLDOWN_AFTER_WIN = 2         # Enfriamiento tras ganar

# Uso de capital de la cuenta: usamos 80% máximo para Trading
MAX_PORTFOLIO_EXPOSURE = 0.80

bot = BinanceConnector()
news = NewsAnalyzer()
estrategia = EstrategiaSmartDCA()
risk_manager = RiskManager()

estado = cargar_estado()

def obtener_balance_total(precio_btc):
    usdt = bot.obtener_saldo_usdt()
    btc  = bot.obtener_saldo_btc()
    return usdt + (btc * precio_btc)

def _usdt_ref(balance_total):
    api_usdt     = bot.obtener_saldo_usdt() or 0.0
    interno_usdt = estado.get('usdt_disponible', 0.0)
    return max(api_usdt, interno_usdt, balance_total)

def reconciliar_estado(precio_actual):
    logger.info("=" * 60)
    logger.info("🔍 RECONCILIANDO ESTADO CON CUENTA REAL...")

    saldo_btc  = bot.obtener_saldo_btc()
    saldo_usdt = bot.obtener_saldo_usdt()

    if saldo_btc is None or saldo_usdt is None:
        logger.warning("⚠️ No se pudo reconciliar: API no disponible.")
        logger.info("=" * 60)
        return

    balance_real = saldo_usdt + (saldo_btc * precio_actual)
    logger.info(f"📡 CUENTA REAL  : {saldo_usdt:.2f} USDT + {saldo_btc:.6f} BTC ≈ {balance_real:.2f} USDT")

    modificado = False

    campos_defecto = {
        'trade_mode':              'smart_dca_15m',
        'usdt_disponible':         0.0,
        'dca_level':               0,
        'total_invested':          0.0,
    }
    for campo, valor in campos_defecto.items():
        if campo not in estado:
            estado[campo] = valor
            modificado = True

    if estado.get('in_position') and saldo_btc < 0.0001:
        logger.info("🔄 CORRECCIÓN: Posición cerrada externamente.")
        estado['in_position'] = False
        estado['amount']      = 0.0
        estado['entry_price'] = 0.0
        estado['dca_level']   = 0
        estado['total_invested'] = 0.0
        modificado = True

    elif estado.get('in_position') and saldo_btc >= 0.0001:
        guardado = estado.get('amount', 0.0)
        diff_pct = abs(guardado - saldo_btc) / (saldo_btc + 1e-9)
        if diff_pct > 0.05:
            logger.info(f"⚖️ AJUSTE DE CANTIDAD: {guardado:.6f} → {saldo_btc:.6f} BTC")
            estado['amount'] = saldo_btc
            modificado = True

    usdt_guardado = estado.get('usdt_disponible', 0.0)
    diff_usdt = abs(usdt_guardado - saldo_usdt) / (saldo_usdt + 1e-9) if saldo_usdt > 0 else 1.0
    if usdt_guardado == 0.0 or diff_usdt > 0.30:
        estado['usdt_disponible'] = saldo_usdt
        modificado = True

    if not estado.get('in_position'):
        if estado.get('entry_price', 0.0) != 0.0:
            estado['entry_price'] = 0.0
            estado['dca_level'] = 0
            estado['total_invested'] = 0.0
            modificado = True

    if modificado:
        guardar_estado(estado)
        logger.info("✅ Estado reconciliado.")
    logger.info("=" * 60)

def main():
    cooldown_counter = 0
    logger.info(f"🤖 AGENTE SMART DCA 15m/1H INICIADO | Mean Reversion | TP: +{TAKE_PROFIT_PCT*100}% | SL Global: -{STOP_LOSS_GLOBAL_PCT*100}%")
    precio_inicial = None
    for _ in range(5):
        precio_inicial = bot.obtener_precio(SYMBOL)
        if precio_inicial: break
        time.sleep(3)

    if precio_inicial: reconciliar_estado(precio_inicial)

    while True:
        try:
            precio = bot.obtener_precio(SYMBOL)
            if not precio:
                time.sleep(PAUSA)
                continue

            balance_total = obtener_balance_total(precio)

            if estado.get('daily_start_balance', 0) == 0:
                estado['daily_start_balance'] = balance_total
                estado['usdt_disponible'] = balance_total
                guardar_estado(estado)

            # =============================================
            # EN POSICIÓN: Smart DCA + TP/SL sobre promedio
            # =============================================
            if estado.get('in_position'):
                saldo_real_btc = bot.obtener_saldo_btc()

                if saldo_real_btc is not None:
                    if saldo_real_btc < 0.0001:
                        # Posición cerrada externamente
                        estado['usdt_disponible'] = _usdt_ref(balance_total)
                        estado['in_position'] = False
                        estado['amount'] = 0
                        estado['dca_level'] = 0
                        estado['total_invested'] = 0.0
                        guardar_estado(estado)
                    elif saldo_real_btc < estado['amount'] * 0.95:
                        estado['amount'] = saldo_real_btc
                        guardar_estado(estado)

                    if estado.get('in_position'):
                        avg_price = estado['entry_price']  # entry_price ES el precio promedio
                        roi_global = (precio - avg_price) / avg_price
                        dca_lvl = estado.get('dca_level', 0)
                        cap_invertido = estado.get('total_invested', 0.0)

                        logger.info(
                            f"💼 15m DCA Lvl {dca_lvl} | P:{precio:.2f} | "
                            f"Promedio:{avg_price:.2f} | ROI:{roi_global*100:.2f}% | "
                            f"Invertido:{cap_invertido:.2f} USDT"
                        )

                        # ----- LÓGICA DE RESCATE DCA -----
                        if dca_lvl < 2:
                            usdt_dispo = bot.obtener_saldo_usdt() or 0.0
                            _, dca1_size, dca2_size = risk_manager.get_dca_allocations(
                                balance_total, MAX_PORTFOLIO_EXPOSURE
                            )

                            hacer_dca = False
                            capital_dca = 0.0
                            nuevo_nivel = dca_lvl

                            if dca_lvl == 0 and roi_global <= -DCA_NIVEL_1_DROP:
                                hacer_dca = True
                                capital_dca = dca1_size
                                nuevo_nivel = 1
                                logger.info(f"🔻 Activando Rescate DCA Nivel 1 (Caída {roi_global*100:.2f}%)")

                            elif dca_lvl == 1 and roi_global <= -DCA_NIVEL_2_DROP:
                                hacer_dca = True
                                capital_dca = dca2_size
                                nuevo_nivel = 2
                                logger.info(f"⏬ Activando Rescate Final DCA Nivel 2 (Caída {roi_global*100:.2f}%)")

                            if hacer_dca and usdt_dispo >= capital_dca * 0.95 and capital_dca > 10:
                                qty_dca = capital_dca / precio
                                orden_dca = bot.crear_orden(SYMBOL, 'buy', qty_dca)
                                if orden_dca:
                                    net_qty_dca = qty_dca * 0.999
                                    total_qty = estado['amount'] + net_qty_dca
                                    # Recalcular precio promedio ponderado
                                    nuevo_promedio = (
                                        (estado['amount'] * avg_price) + (net_qty_dca * precio)
                                    ) / total_qty
                                    estado['amount'] = total_qty
                                    estado['entry_price'] = nuevo_promedio
                                    estado['dca_level'] = nuevo_nivel
                                    estado['total_invested'] = cap_invertido + capital_dca
                                    estado['usdt_disponible'] = max(0.0, usdt_dispo - capital_dca)
                                    guardar_estado(estado)
                                    logger.info(
                                        f"✅ DCA Nivel {nuevo_nivel} ejecutado a {precio:.2f} "
                                        f"| Nuevo Promedio: {nuevo_promedio:.2f} "
                                        f"| Total BTC: {total_qty:.6f}"
                                    )
                                    time.sleep(PAUSA)
                                    continue

                        # ----- LÓGICA DE SALIDA TP / SL -----
                        vender = False
                        motivo = ""

                        if roi_global >= TAKE_PROFIT_PCT:
                            vender = True
                            motivo = f"TAKE PROFIT ({roi_global*100:.2f}% sobre promedio {avg_price:.2f})"

                        elif roi_global <= -STOP_LOSS_GLOBAL_PCT:
                            vender = True
                            motivo = f"STOP LOSS GLOBAL ({roi_global*100:.2f}%) 🔥"

                        if vender:
                            logger.info(f"🛑 SALIDA: {motivo} a {precio:.2f}")
                            saldo_real_btc = bot.obtener_saldo_btc()
                            cantidad_vender = (
                                min(estado['amount'], saldo_real_btc)
                                if (saldo_real_btc and saldo_real_btc > 0.0001)
                                else estado['amount']
                            )
                            bot.crear_orden(SYMBOL, 'sell', cantidad_vender)

                            proceeds_brutos = precio * cantidad_vender
                            fee_venta = proceeds_brutos * 0.001
                            proceeds_netos = proceeds_brutos - fee_venta
                            pnl = proceeds_netos - cap_invertido

                            logger.info(f"💸 FEE VENTA: {fee_venta:.2f} USDT | PnL: {pnl:+.2f} USDT")

                            if 'STOP LOSS' in motivo:
                                cooldown_counter = COOLDOWN_AFTER_SL
                                logger.info(f"⏳ Cooldown SL: {COOLDOWN_AFTER_SL} ciclos ({COOLDOWN_AFTER_SL * PAUSA // 60}min)")
                            else:
                                cooldown_counter = COOLDOWN_AFTER_WIN
                                logger.info(f"⏳ Cooldown Win: {COOLDOWN_AFTER_WIN} ciclo")

                            estado['usdt_disponible'] = (estado.get('usdt_disponible', 0) + proceeds_netos)
                            estado['in_position'] = False
                            estado['amount'] = 0
                            estado['dca_level'] = 0
                            estado['total_invested'] = 0.0
                            guardar_estado(estado)
                            logger.info(f"💰 Trade cerrado. Capital: {estado['usdt_disponible']:.2f} USDT")

            # =============================================
            # SIN POSICIÓN: Buscar señal de entrada
            # =============================================
            else:
                if cooldown_counter > 0:
                    cooldown_counter -= 1
                    logger.info(f"⏳ Cooldown: {cooldown_counter} ciclos restantes. P:{precio:.2f}")
                    time.sleep(PAUSA)
                    continue

                sentiment_score = news.obtener_sentimiento()

                # Solo bloqueamos si pánico absoluto (en DCA somos más valientes ante el miedo)
                if sentiment_score < -0.95:
                    logger.info(f"🔴 PÁNICO ABSOLUTO ({sentiment_score:.2f}). Esperando...")
                    time.sleep(PAUSA)
                    continue

                # Obtener velas 15m (señal) y 1h (filtro macro)
                velas_15m = bot.obtener_velas(SYMBOL, timeframe=TIMEFRAME, limit=100)
                velas_1h  = bot.obtener_velas(SYMBOL, timeframe=TIMEFRAME_TREND, limit=100)
                if not velas_15m:
                    time.sleep(PAUSA)
                    continue

                macro_ok = estrategia.analizar_filtro_1h(velas_1h)
                senal_compra, atr_actual, modo = estrategia.analizar(velas_15m)

                if senal_compra and macro_ok:
                    usdt_ref = _usdt_ref(balance_total)
                    c_base, _, _ = risk_manager.get_dca_allocations(balance_total, MAX_PORTFOLIO_EXPOSURE)
                    capital_compra = min(c_base, usdt_ref * 0.98)
                    cantidad_a_comprar = capital_compra / precio

                    if capital_compra > 10:
                        logger.info(
                            f"🚀 SEÑAL {modo}! BASE entrada con {capital_compra:.2f} USDT "
                            f"({capital_compra/balance_total*100:.1f}% del capital)"
                        )
                        orden = bot.crear_orden(SYMBOL, 'buy', cantidad_a_comprar)
                        if orden:
                            net_qty = cantidad_a_comprar * 0.999
                            estado['in_position']    = True
                            estado['entry_price']    = precio   # precio promedio inicial
                            estado['amount']         = net_qty
                            estado['dca_level']      = 0
                            estado['total_invested'] = capital_compra
                            estado['entry_mode']     = modo
                            estado['entry_time']     = time.time()
                            estado['usdt_disponible'] = usdt_ref - capital_compra
                            guardar_estado(estado)
                            logger.info(
                                f"🚀 ENTRADA DCA BASE a {precio:.2f} "
                                f"| TP prom: +{TAKE_PROFIT_PCT*100:.2f}% "
                                f"| DCA1/{DCA_NIVEL_1_DROP*100:.0f}% DCA2/{DCA_NIVEL_2_DROP*100:.0f}% "
                                f"| SL Global: -{STOP_LOSS_GLOBAL_PCT*100:.0f}%"
                            )
                elif senal_compra and not macro_ok:
                    logger.info(f"⚠️ Señal 15m ignorada: Filtro Macro 1H bajista (precio < EMA50*0.95)")
                else:
                    logger.info(f"👀 Escaneando 15m | P:{precio:.2f} | Sent:{sentiment_score:.2f}")

            time.sleep(PAUSA)

        except Exception as e:
            logger.error(f"❌ Error Loop: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()
