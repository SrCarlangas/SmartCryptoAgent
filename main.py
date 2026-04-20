import math
import time
from modules.binance_api import BinanceConnector
from modules.sentiment import NewsAnalyzer
from modules.strategy import EstrategiaSmartDCA
from modules.risk import RiskManager
from modules.regime import RegimeDetector
from modules.utils import (
    cargar_estado, guardar_estado, generar_position_id,
    get_total_btc_positions, get_total_invested, has_open_positions,
    get_position_by_id, remove_position,
    registrar_decision_agente, registrar_trade, get_recent_trades_summary,
    get_recent_decisions_summary, calcular_avg_entrada_desde_historial,
)
from modules.logger import logger
from modules.market_data import build_market_context
from modules.trigger_evaluator import TriggerEvaluator
from modules.agent.orchestrator import AgentOrchestrator
from modules.agent.models import ExecutionPlan
from config import (
    SYMBOL, TIMEFRAME, TIMEFRAME_TREND, TIMEFRAME_WEEKLY, PAUSA,
    CANDLES_15M, CANDLES_1H, CANDLES_1W,
    TAKE_PROFIT_PCT, STOP_LOSS_GLOBAL_PCT, HARD_STOP_LOSS_PCT,
    DCA_NIVEL_1_DROP, DCA_NIVEL_2_DROP,
    MAX_PORTFOLIO_EXPOSURE, COOLDOWN_AFTER_SL, COOLDOWN_AFTER_WIN,
    AGENT_MODE, MIN_POSITION_CAPITAL,
    MAX_CONCURRENT_POSITIONS, REGIME_PARAMS,
)

bot = BinanceConnector()
news = NewsAnalyzer()
estrategia = EstrategiaSmartDCA()
risk_manager = RiskManager()
trigger_eval = TriggerEvaluator()
orchestrator = AgentOrchestrator(risk_manager, estrategia)
regime_detector = RegimeDetector()

estado = cargar_estado()


def _truncar_btc(cantidad):
    """Trunca cantidad BTC a 5 decimales (Binance step size para BTC/USDT)."""
    return math.floor(cantidad * 100000) / 100000


def _extraer_datos_orden(orden):
    """Extrae precio real, cantidad ejecutada y costo real de una orden de Binance.
    ccxt normaliza: average (precio promedio), filled (cantidad ejecutada), cost (USDT total).
    """
    precio_real = float(orden.get('average', 0) or 0)
    cantidad_real = float(orden.get('filled', 0) or 0)
    costo_real = float(orden.get('cost', 0) or 0)
    fee_total = 0.0
    # ccxt puede devolver fee como dict o dentro de fees como lista
    if orden.get('fee') and orden['fee'].get('cost'):
        fee_total = float(orden['fee']['cost'])
    elif orden.get('fees'):
        fee_total = sum(float(f.get('cost', 0)) for f in orden['fees'])
    return precio_real, cantidad_real, costo_real, fee_total


def obtener_balance_total(precio_btc):
    usdt = bot.obtener_saldo_usdt()
    btc = bot.obtener_saldo_btc()
    return usdt + (btc * precio_btc)


def _usdt_ref(balance_total):
    api_usdt = bot.obtener_saldo_usdt() or 0.0
    interno_usdt = estado.get('usdt_disponible', 0.0)
    return max(api_usdt, interno_usdt, balance_total)


def reconciliar_estado(precio_actual):
    logger.info("=" * 60)
    logger.info("🔍 RECONCILIANDO ESTADO CON CUENTA REAL...")

    saldo_btc = bot.obtener_saldo_btc()
    saldo_usdt = bot.obtener_saldo_usdt()

    if saldo_btc is None or saldo_usdt is None:
        logger.warning("⚠️ No se pudo reconciliar: API no disponible.")
        logger.info("=" * 60)
        return

    balance_real = saldo_usdt + (saldo_btc * precio_actual)
    logger.info(f"📡 CUENTA REAL  : {saldo_usdt:.2f} USDT + {saldo_btc:.6f} BTC ≈ {balance_real:.2f} USDT")

    positions = estado.get('positions', [])
    expected_btc = get_total_btc_positions(estado)
    modificado = False

    # Si no hay BTC real pero hay posiciones virtuales: cerrar todas
    if positions and saldo_btc < 0.0001:
        logger.info("🔄 CORRECCIÓN: Todas las posiciones cerradas externamente.")
        estado['positions'] = []
        modificado = True

    # Si NO hay posiciones pero SI hay BTC real: BTC huérfano → crear posicion virtual
    elif not positions and saldo_btc >= 0.0001:
        avg_precio, total_costo = calcular_avg_entrada_desde_historial(estado, saldo_btc)
        if avg_precio is not None:
            ref_nota = f"Avg ponderado desde historial: ${avg_precio:.2f}"
        else:
            avg_precio = precio_actual
            total_costo = saldo_btc * precio_actual
            ref_nota = f"Precio de mercado (historial insuficiente): ${precio_actual:.2f}"
        logger.info(
            f"🔄 RECUPERACIÓN: BTC huérfano detectado: {saldo_btc:.6f} BTC "
            f"(≈ ${total_costo:.2f}) sin posición virtual."
        )
        pos_id = generar_position_id()
        new_pos = {
            'id': pos_id,
            'entry_price': avg_precio,
            'amount': saldo_btc,
            'dca_level': 0,
            'total_invested': total_costo,
            'entry_time': time.time(),
            'entry_mode': 'recovered_orphan',
            'is_orphan': True,
            'is_frozen': True,  # siempre frozen: visible para el agente pero no se compra/DCA
            'exits_taken': [],
        }
        estado['positions'] = [new_pos]
        logger.warning(
            f"⚠️ Posición virtual {pos_id} creada para BTC huérfano (CONGELADA). "
            f"Entrada: {ref_nota}. "
            f"Se venderá automáticamente vía trailing stop."
        )
        modificado = True

    # Si hay BTC y posiciones, ajustar proporcionalmente si hay drift > 5%
    elif positions and saldo_btc >= 0.0001 and expected_btc > 0:
        diff_pct = abs(expected_btc - saldo_btc) / expected_btc
        if diff_pct > 0.05:
            ratio = saldo_btc / expected_btc
            for p in positions:
                p['amount'] = p.get('amount', 0) * ratio
            logger.info(f"⚖️ AJUSTE PROPORCIONAL: ratio {ratio:.4f} aplicado a {len(positions)} posiciones")
            modificado = True

    # Sincronizar USDT
    usdt_guardado = estado.get('usdt_disponible', 0.0)
    diff_usdt = abs(usdt_guardado - saldo_usdt) / (saldo_usdt + 1e-9) if saldo_usdt > 0 else 1.0
    if usdt_guardado == 0.0 or diff_usdt > 0.30:
        estado['usdt_disponible'] = saldo_usdt
        modificado = True

    if modificado:
        guardar_estado(estado)
        logger.info("✅ Estado reconciliado.")

    num_pos = len(estado.get('positions', []))
    total_inv = get_total_invested(estado)
    logger.info(f"📊 Posiciones: {num_pos} | Invertido: ${total_inv:.2f} | USDT libre: {estado.get('usdt_disponible', 0):.2f}")
    logger.info("=" * 60)


def _ejecutar_compra(plan, precio, balance_total):
    """Abre una nueva posicion."""
    usdt_dispo = bot.obtener_saldo_usdt() or 0.0
    capital_compra = min(plan.capital, usdt_dispo * 0.98)

    if capital_compra < MIN_POSITION_CAPITAL:
        logger.info(f"⚠️ Capital insuficiente para nueva posicion: {capital_compra:.2f} USDT")
        return

    cantidad = _truncar_btc(capital_compra / precio)
    if cantidad < 0.00001:
        logger.info(f"⚠️ Cantidad BTC demasiado pequeña: {cantidad}")
        return
    logger.info(
        f"🚀 NUEVA POSICION con {capital_compra:.2f} USDT "
        f"({capital_compra/balance_total*100:.1f}% del capital) | {plan.source}"
    )
    orden = bot.crear_orden(SYMBOL, 'buy', cantidad)
    if orden:
        precio_real, cantidad_real, costo_real, _ = _extraer_datos_orden(orden)
        entry_price = precio_real if precio_real > 0 else precio
        net_qty = cantidad_real if cantidad_real > 0 else cantidad * 0.999
        total_cost = costo_real if costo_real > 0 else capital_compra

        pos_id = generar_position_id()
        new_pos = {
            'id': pos_id,
            'entry_price': entry_price,
            'amount': net_qty,
            'dca_level': 0,
            'total_invested': total_cost,
            'entry_time': time.time(),
            'entry_mode': plan.reasoning[:50],
            'exits_taken': [],
        }
        estado['positions'].append(new_pos)
        estado['usdt_disponible'] = max(0, usdt_dispo - total_cost)
        registrar_decision_agente(estado, plan.source, "BUY", 0.0, plan.reasoning)
        guardar_estado(estado)
        num = len(estado['positions'])
        logger.info(
            f"✅ Posicion {pos_id} abierta a ${entry_price:.2f} (real) | "
            f"BTC: {net_qty:.6f} | Costo: ${total_cost:.2f} | Posiciones activas: {num}"
        )


def _ejecutar_dca(plan, precio):
    """Ejecuta DCA en una posicion especifica."""
    pos = get_position_by_id(estado, plan.target_position_id)
    if not pos:
        logger.warning(f"⚠️ Posicion {plan.target_position_id} no encontrada para DCA")
        return

    usdt_dispo = bot.obtener_saldo_usdt() or 0.0
    capital_dca = min(plan.capital, usdt_dispo * 0.98)
    nuevo_nivel = pos.get('dca_level', 0) + 1

    if capital_dca < MIN_POSITION_CAPITAL or usdt_dispo < capital_dca * 0.95:
        logger.info(f"⚠️ Capital insuficiente para DCA: {capital_dca:.2f} USDT")
        return

    logger.info(f"🔻 DCA Nivel {nuevo_nivel} para [{plan.target_position_id}] | Capital: {capital_dca:.2f}")
    qty_dca = _truncar_btc(capital_dca / precio)
    if qty_dca < 0.00001:
        logger.info(f"⚠️ Cantidad BTC demasiado pequeña para DCA: {qty_dca}")
        return
    orden = bot.crear_orden(SYMBOL, 'buy', qty_dca)
    if orden:
        precio_real, cantidad_real, costo_real, _ = _extraer_datos_orden(orden)
        dca_price = precio_real if precio_real > 0 else precio
        net_qty_dca = cantidad_real if cantidad_real > 0 else qty_dca * 0.999
        dca_cost = costo_real if costo_real > 0 else capital_dca

        old_amount = pos['amount']
        old_avg = pos['entry_price']
        total_qty = old_amount + net_qty_dca
        nuevo_promedio = ((old_amount * old_avg) + (net_qty_dca * dca_price)) / total_qty

        pos['amount'] = total_qty
        pos['entry_price'] = nuevo_promedio
        pos['dca_level'] = nuevo_nivel
        pos['total_invested'] = pos.get('total_invested', 0) + dca_cost
        estado['usdt_disponible'] = max(0, usdt_dispo - dca_cost)
        registrar_decision_agente(estado, plan.source, "DCA", 0.0, plan.reasoning)
        guardar_estado(estado)
        logger.info(
            f"✅ DCA Nivel {nuevo_nivel} [{plan.target_position_id}] a ${dca_price:.2f} (real) | "
            f"Nuevo Promedio: ${nuevo_promedio:.2f} | BTC: {total_qty:.6f}"
        )


def _ejecutar_venta(plan, precio, cooldown_counter):
    """Cierra una posicion especifica (venta total)."""
    pos = get_position_by_id(estado, plan.target_position_id)
    if not pos:
        logger.warning(f"⚠️ Posicion {plan.target_position_id} no encontrada para SELL")
        return cooldown_counter

    cantidad_vender = pos.get('amount', 0)
    if cantidad_vender < 0.00001:
        remove_position(estado, plan.target_position_id)
        guardar_estado(estado)
        return cooldown_counter

    # Verificar saldo real de BTC y ajustar cantidad
    saldo_real_btc = bot.obtener_saldo_btc()
    if saldo_real_btc is not None:
        if saldo_real_btc < 0.00001:
            logger.warning(f"⚠️ [{plan.target_position_id}] Sin BTC real. Cerrando posicion virtual.")
            cap_invertido = pos.get('total_invested', 0)
            remove_position(estado, plan.target_position_id)
            estado['usdt_disponible'] = estado.get('usdt_disponible', 0) + cap_invertido
            guardar_estado(estado)
            return cooldown_counter
        cantidad_vender = min(cantidad_vender, saldo_real_btc)

    cantidad_vender = _truncar_btc(cantidad_vender)
    if cantidad_vender < 0.00001:
        logger.warning(f"⚠️ [{plan.target_position_id}] Cantidad BTC truncada a 0. Cerrando posicion virtual.")
        cap_invertido = pos.get('total_invested', 0)
        remove_position(estado, plan.target_position_id)
        estado['usdt_disponible'] = estado.get('usdt_disponible', 0) + cap_invertido
        guardar_estado(estado)
        return cooldown_counter

    if pos.get('is_frozen'):
        logger.info(f"🔓 VENDIENDO posicion CONGELADA [{plan.target_position_id}]: ROI aprox ${(precio/pos['entry_price']-1)*100:.1f}% a ${precio:.2f}")
    logger.info(f"🛑 CERRANDO [{plan.target_position_id}]: {plan.reasoning} a ${precio:.2f}")
    orden = bot.crear_orden(SYMBOL, 'sell', cantidad_vender)

    if not orden:
        logger.error(f"❌ Orden de venta fallo para [{plan.target_position_id}]")
        return cooldown_counter

    precio_real, cantidad_real, costo_real, fee_real = _extraer_datos_orden(orden)
    sell_price = precio_real if precio_real > 0 else precio
    sold_qty = cantidad_real if cantidad_real > 0 else cantidad_vender
    proceeds_brutos = costo_real if costo_real > 0 else sell_price * sold_qty
    fee_venta = fee_real if fee_real > 0 else proceeds_brutos * 0.001

    cap_invertido = pos.get('total_invested', 0)
    proceeds_netos = proceeds_brutos - fee_venta
    pnl = proceeds_netos - cap_invertido

    logger.info(
        f"💸 [{plan.target_position_id}] Precio real: ${sell_price:.2f} | "
        f"FEE: {fee_venta:.2f} | PnL: {pnl:+.2f} USDT"
    )

    is_stop_loss = "stop" in plan.reasoning.lower() or "sl" in plan.reasoning.lower()
    if is_stop_loss:
        cooldown_counter = COOLDOWN_AFTER_SL
        logger.info(f"⏳ Cooldown SL: {COOLDOWN_AFTER_SL} ciclos")
    else:
        cooldown_counter = COOLDOWN_AFTER_WIN
        logger.info(f"⏳ Cooldown Win: {COOLDOWN_AFTER_WIN} ciclos")

    registrar_trade(estado, "SELL", precio, cantidad_vender, pnl, fee=fee_venta)
    remove_position(estado, plan.target_position_id)
    estado['usdt_disponible'] = estado.get('usdt_disponible', 0) + proceeds_netos
    guardar_estado(estado)

    # PnL real acumulado basado en balance (siempre correcto)
    capital_ini = estado.get('capital_inicial', 0)
    btc_restante = get_total_btc_positions(estado)
    balance_post = estado['usdt_disponible'] + (btc_restante * precio)
    pnl_real = balance_post - capital_ini if capital_ini > 0 else 0

    if pos.get('is_orphan'):
        logger.warning(
            f"⚠️ PnL de posición huérfana {plan.target_position_id} es aproximado. "
            f"Usar PnL real (balance) como referencia."
        )

    logger.info(
        f"📊 PnL trade: {pnl:+.2f} | PnL acumulado (trades): {estado.get('total_pnl', 0):+.2f} | "
        f"PnL real (balance): {pnl_real:+.2f} | Fees totales: {estado.get('total_fees', 0):.2f}"
    )

    num_restantes = len(estado.get('positions', []))
    logger.info(f"💰 Posicion cerrada. Posiciones restantes: {num_restantes} | USDT: {estado['usdt_disponible']:.2f}")

    return cooldown_counter


def _ejecutar_venta_parcial(plan, precio, cooldown_counter):
    """Vende una fraccion de una posicion (PARTIAL_SELL)."""
    pos = get_position_by_id(estado, plan.target_position_id)
    if not pos:
        logger.warning(f"⚠️ Posicion {plan.target_position_id} no encontrada para PARTIAL_SELL")
        return cooldown_counter

    sell_pct = plan.sell_pct
    cantidad = _truncar_btc(pos['amount'] * sell_pct)
    if cantidad < 0.00001:
        logger.info(f"⚠️ Cantidad parcial demasiado pequeña para [{plan.target_position_id}]")
        return cooldown_counter

    # Guard notional mínimo Binance (~10 USDT). Si el parcial queda por debajo,
    # liquidar la posición completa en lugar de fallar con -1013 NOTIONAL.
    if cantidad * precio < 10.0:
        cantidad_total = _truncar_btc(pos['amount'])
        if cantidad_total * precio < 10.0:
            logger.info(
                f"⚠️ [{plan.target_position_id}] posicion demasiado pequeña "
                f"(${cantidad_total*precio:.2f} < $10 notional), omitiendo"
            )
            return cooldown_counter
        logger.info(
            f"⚠️ Partial {sell_pct*100:.0f}% = ${cantidad*precio:.2f} < $10 notional. "
            f"Liquidando posicion completa [{plan.target_position_id}]."
        )
        cantidad = cantidad_total
        sell_pct = 1.0

    # Guard anti-fragmentación: si el restante tras el parcial vale < 2x capital mínimo,
    # liquidar completo para evitar cascada de micro-ventas con fees desproporcionadas.
    if 0 < sell_pct < 1.0:
        restante_btc = pos.get('amount', 0) - cantidad
        restante_valor = restante_btc * precio
        if 0 < restante_valor < MIN_POSITION_CAPITAL * 2:
            cantidad_total = _truncar_btc(pos['amount'])
            if cantidad_total * precio >= 10.0:
                logger.info(
                    f"⬆️ PARTIAL→SELL [{plan.target_position_id}]: restante "
                    f"${restante_valor:.0f} < ${MIN_POSITION_CAPITAL*2:.0f}. Liquidando completo."
                )
                cantidad = cantidad_total
                sell_pct = 1.0

    # Verificar saldo real
    saldo_real_btc = bot.obtener_saldo_btc()
    if saldo_real_btc is not None:
        cantidad = min(cantidad, _truncar_btc(saldo_real_btc))
    if cantidad < 0.00001:
        return cooldown_counter

    logger.info(
        f"📉 PARTIAL_SELL [{plan.target_position_id}] {sell_pct*100:.0f}% "
        f"({cantidad:.6f} BTC) | {plan.exit_trigger}"
    )
    orden = bot.crear_orden(SYMBOL, 'sell', cantidad)
    if not orden:
        logger.error(f"❌ Orden parcial fallo para [{plan.target_position_id}]")
        return cooldown_counter

    precio_real, cantidad_real, costo_real, fee_real = _extraer_datos_orden(orden)
    proceeds_brutos = costo_real if costo_real > 0 else (precio_real or precio) * (cantidad_real or cantidad)
    fee_venta = fee_real if fee_real > 0 else proceeds_brutos * 0.001
    proceeds_netos = proceeds_brutos - fee_venta

    # Actualizar posicion (NO eliminar)
    sold_qty = cantidad_real if cantidad_real > 0 else cantidad
    total_invested_pre = pos.get('total_invested', 0)
    pos['amount'] -= sold_qty
    pos['total_invested'] *= (1 - sell_pct)
    pos.setdefault('exits_taken', []).append(plan.exit_trigger)

    # PnL parcial (proporcional). Liquidacion total usa formula directa.
    if sell_pct >= 1.0:
        pnl_parcial = proceeds_netos - total_invested_pre
    else:
        pnl_parcial = proceeds_netos - (pos['total_invested'] * sell_pct / (1 - sell_pct + 1e-9))
    registrar_trade(estado, "PARTIAL_SELL", precio, sold_qty, pnl_parcial, fee=fee_venta)

    # Si queda dust, cerrar totalmente
    if pos['amount'] < 0.00001:
        remove_position(estado, plan.target_position_id)
        logger.info(f"🧹 Posicion [{plan.target_position_id}] cerrada por dust despues de partial sell")

    estado['usdt_disponible'] = estado.get('usdt_disponible', 0) + proceeds_netos
    guardar_estado(estado)

    # PnL real acumulado
    capital_ini = estado.get('capital_inicial', 0)
    btc_restante = get_total_btc_positions(estado)
    balance_post = estado['usdt_disponible'] + (btc_restante * precio)
    pnl_real = balance_post - capital_ini if capital_ini > 0 else 0

    logger.info(
        f"✅ Partial sell [{plan.target_position_id}]: {sell_pct*100:.0f}% vendido | "
        f"Restante: {pos.get('amount', 0):.6f} BTC | +{proceeds_netos:.2f} USDT"
    )
    logger.info(
        f"📊 PnL parcial: {pnl_parcial:+.2f} | PnL acumulado: {estado.get('total_pnl', 0):+.2f} | "
        f"PnL real (balance): {pnl_real:+.2f}"
    )
    return cooldown_counter


def _check_hard_limits(precio, cooldown_counter):
    """Verifica SL de emergencia universal en TODAS las posiciones (sin necesidad de trigger).
    El TP por regimen se maneja en el orchestrator.
    """
    positions = estado.get('positions', [])
    for pos in positions[:]:
        roi = (precio - pos['entry_price']) / pos['entry_price'] if pos['entry_price'] > 0 else 0

        if roi <= -HARD_STOP_LOSS_PCT:
            logger.info(f"🛑 HARD STOP LOSS [{pos['id']}] ROI: {roi*100:.2f}% (limite -{HARD_STOP_LOSS_PCT*100:.0f}%)")
            sl_plan = ExecutionPlan(
                action="SELL", target_position_id=pos['id'],
                reasoning=f"HARD STOP LOSS ({roi*100:.2f}%)", source="hard_limit"
            )
            cooldown_counter = _ejecutar_venta(sl_plan, precio, cooldown_counter)

    return cooldown_counter


def main():
    cooldown_counter = 0
    logger.info("=" * 70)
    logger.info("🤖 SmartCryptoAgent v4 — Anti-Peak-Buying Edition")
    logger.info(f"   Modo: {AGENT_MODE} | Hard SL: -{HARD_STOP_LOSS_PCT*100:.0f}%")
    logger.info("   ✅ Peak Guard: bloquea BUY si precio <1% del swing_high 48h")
    logger.info("   ✅ ADX Filter: bloquea BUY si 1h -DI > +DI + 5 pts (bajista)")
    logger.info("   ✅ ALCISTA MOMENTUM RSI: 35-55 (era 35-65)")
    logger.info("   ✅ Cooldown post-win: 20 ciclos / 10 min (era 2 / 1 min)")
    logger.info("   ✅ Anti-fragmentación PARTIAL_SELL: máx 2 transacciones")
    logger.info("   ✅ LATERAL MOMENTUM RSI: 35-65 (era 35-62)")
    logger.info("=" * 70)

    precio_inicial = None
    for _ in range(5):
        precio_inicial = bot.obtener_precio(SYMBOL)
        if precio_inicial:
            break
        time.sleep(3)

    if precio_inicial:
        reconciliar_estado(precio_inicial)

    ciclo_count = 0
    while True:
        try:
            ciclo_count += 1
            precio = bot.obtener_precio(SYMBOL)
            if not precio:
                time.sleep(PAUSA)
                continue

            balance_total = obtener_balance_total(precio)

            if estado.get('daily_start_balance', 0) == 0:
                estado['daily_start_balance'] = balance_total
                estado['usdt_disponible'] = balance_total
                guardar_estado(estado)

            # Capital inicial: se setea al arrancar. Si el valor guardado excede
            # 2x el balance real reconciliado, probablemente es herencia de Demo.
            capital_guardado = estado.get('capital_inicial', 0)
            if capital_guardado == 0:
                estado['capital_inicial'] = balance_total
                guardar_estado(estado)
                logger.info(f"📊 Capital inicial registrado: ${balance_total:.2f}")
            elif capital_guardado > balance_total * 2.0:
                logger.warning(
                    f"⚠️ capital_inicial ${capital_guardado:.2f} excede 2x el balance real "
                    f"${balance_total:.2f} (posible herencia de sesion Demo). Corrigiendo."
                )
                estado['capital_inicial'] = balance_total
                guardar_estado(estado)

            # Log periódico de rendimiento (~10min = cada 20 ciclos de 30s)
            if ciclo_count % 20 == 0 and estado.get('capital_inicial', 0) > 0:
                pnl_real = balance_total - estado['capital_inicial']
                pnl_pct = (pnl_real / estado['capital_inicial']) * 100
                logger.info(
                    f"📊 RENDIMIENTO | Capital ini: ${estado['capital_inicial']:.2f} | "
                    f"Balance: ${balance_total:.2f} | PnL real: {pnl_real:+.2f} ({pnl_pct:+.2f}%) | "
                    f"Trades: {estado.get('total_trades', 0)} | Fees: ${estado.get('total_fees', 0):.2f}"
                )

            # Reconciliar BTC real vs posiciones virtuales
            positions = estado.get('positions', [])
            saldo_real_btc = bot.obtener_saldo_btc()
            if saldo_real_btc is not None:
                if positions and saldo_real_btc < 0.0001:
                    logger.info("🔄 BTC real = 0. Cerrando todas las posiciones virtuales.")
                    estado['positions'] = []
                    estado['usdt_disponible'] = _usdt_ref(balance_total)
                    guardar_estado(estado)
                elif not positions and saldo_real_btc >= 0.0001:
                    # Intentar calcular el precio promedio real desde el historial de trades
                    avg_precio, total_costo = calcular_avg_entrada_desde_historial(
                        estado, saldo_real_btc
                    )
                    if avg_precio is not None:
                        ref_nota = f"Avg desde historial: ${avg_precio:.2f}"
                    else:
                        avg_precio = precio
                        total_costo = saldo_real_btc * precio
                        ref_nota = f"Avg de mercado (historial insuficiente): ${precio:.2f}"
                    pos_id = generar_position_id()
                    new_pos = {
                        'id': pos_id,
                        'entry_price': avg_precio,
                        'amount': saldo_real_btc,
                        'dca_level': 0,
                        'total_invested': total_costo,
                        'entry_time': time.time(),
                        'entry_mode': 'recovered_orphan',
                        'is_orphan': True,
                        'is_frozen': True,
                        'exits_taken': [],
                    }
                    estado['positions'] = [new_pos]
                    guardar_estado(estado)
                    logger.warning(
                        f"⚠️ BTC huérfano recuperado: {saldo_real_btc:.6f} BTC → posición {pos_id} (CONGELADA). "
                        f"{ref_nota}. No se operará automáticamente."
                    )

            # Cooldown global (solo bloquea nuevas compras, no gestiona existentes)
            if cooldown_counter > 0:
                cooldown_counter -= 1
                if not has_open_positions(estado):
                    logger.info(f"⏳ Cooldown: {cooldown_counter} ciclos restantes. P:{precio:.2f}")
                    time.sleep(PAUSA)
                    continue

            # Hard SL: siempre se evalua en cada ciclo
            cooldown_counter = _check_hard_limits(precio, cooldown_counter)

            # Obtener sentimiento (siempre, necesario para deteccion de crash)
            sentiment_score, fear_greed_raw = news.obtener_sentimiento()

            # Obtener velas
            velas_15m = bot.obtener_velas(SYMBOL, timeframe=TIMEFRAME, limit=CANDLES_15M)
            velas_1h = bot.obtener_velas(SYMBOL, timeframe=TIMEFRAME_TREND, limit=CANDLES_1H)
            velas_1w = bot.obtener_velas(SYMBOL, timeframe=TIMEFRAME_WEEKLY, limit=CANDLES_1W)

            if not velas_15m:
                time.sleep(PAUSA)
                continue

            # Construir contexto con todos los indicadores
            ctx = build_market_context(
                velas_15m, velas_1h, velas_1w,
                precio, sentiment_score, fear_greed_raw,
                estado, balance_total
            )
            ctx.cooldown_active = cooldown_counter > 0
            ctx.recent_trades_summary = get_recent_trades_summary(estado)
            ctx.recent_decisions_summary = get_recent_decisions_summary(estado)

            # Trailing stop: actualizar peak_price en TODAS las posiciones (incluye frozen).
            # Las frozen pueden venderse via trailing aunque no via DCA/nuevas entradas.
            # Se guarda en el estado para sobrevivir reinicios.
            trailing_activation = REGIME_PARAMS.get(ctx.regime, {}).get('tp_pct', 0.010)
            peak_updated = False
            for pos_dict in estado.get('positions', []):
                entry_price = pos_dict.get('entry_price', 0)
                if entry_price <= 0:
                    continue
                roi_now = (precio - entry_price) / entry_price
                if roi_now >= trailing_activation:
                    if precio > pos_dict.get('peak_price', 0):
                        pos_dict['peak_price'] = precio
                        peak_updated = True
            if peak_updated:
                guardar_estado(estado)

            # PnL real del portafolio
            capital_ini = estado.get('capital_inicial', 0)
            if capital_ini > 0:
                ctx.capital_inicial = capital_ini
                ctx.portfolio_pnl = balance_total - capital_ini
                ctx.portfolio_pnl_pct = ctx.portfolio_pnl / capital_ini

            # Detectar regimen de mercado
            regime_result = regime_detector.detect(ctx)
            ctx.regime = regime_result.regime
            ctx.regime_confidence = regime_result.confidence

            # Actualizar slots disponibles segun regimen (limites adaptativos)
            from config import REGIME_PARAMS as _rp
            regime_max_pos = _rp.get(ctx.regime, {}).get("max_positions", MAX_CONCURRENT_POSITIONS)
            ctx.available_slots = max(0, regime_max_pos - ctx.num_positions)

            logger.info(
                f"📊 REGIMEN: {regime_result.regime} ({regime_result.confidence:.0%}) | {regime_result.details}"
                f" | Slots: {ctx.available_slots}/{regime_max_pos}"
            )

            # Evaluar si debemos llamar al agente
            should_call = trigger_eval.should_call_agent(ctx)

            if not should_call:
                if has_open_positions(estado):
                    for pos in estado['positions']:
                        roi = (precio - pos['entry_price']) / pos['entry_price'] if pos['entry_price'] > 0 else 0
                        logger.info(
                            f"💼 [{pos['id']}] DCA:{pos.get('dca_level',0)} | "
                            f"P:{precio:.2f} | Avg:{pos['entry_price']:.2f} | ROI:{roi*100:.2f}%"
                        )
                else:
                    logger.info(f"👀 Escaneando | P:{precio:.2f} | Sent:{sentiment_score:.2f} | Posiciones: 0")

                trigger_eval.force_update(ctx)
                time.sleep(PAUSA)
                continue

            # === DECISION AGENTICA ===
            plan = orchestrator.decide(ctx, velas_15m, velas_1h)

            registrar_decision_agente(estado, plan.source, plan.action, 0.0, plan.reasoning)

            if plan.vetoed:
                logger.info(f"🛡️ Decision vetada: {plan.veto_reason}")
                time.sleep(PAUSA)
                continue

            # Ejecutar accion
            if plan.action == "BUY":
                if cooldown_counter <= 0:
                    _ejecutar_compra(plan, precio, balance_total)
                else:
                    logger.info(f"⏳ BUY bloqueado por cooldown ({cooldown_counter} ciclos)")

            elif plan.action == "DCA" and plan.target_position_id:
                _ejecutar_dca(plan, precio)

            elif plan.action == "SELL" and plan.target_position_id:
                cooldown_counter = _ejecutar_venta(plan, precio, cooldown_counter)

            elif plan.action == "PARTIAL_SELL" and plan.target_position_id:
                cooldown_counter = _ejecutar_venta_parcial(plan, precio, cooldown_counter)

            time.sleep(PAUSA)

        except Exception as e:
            logger.error(f"❌ Error Loop: {e}")
            time.sleep(10)


if __name__ == "__main__":
    main()
