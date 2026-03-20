import json
import os
import time
from datetime import datetime

STATE_FILE = 'bot_state.json'


def cargar_estado():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                estado = json.load(f)

                # MIGRACION: formato viejo (single position) -> nuevo (multi-position)
                if 'in_position' in estado and 'positions' not in estado:
                    positions = []
                    if estado.get('in_position') and estado.get('amount', 0) > 0:
                        positions.append({
                            'id': f"pos_{int(estado.get('entry_time', time.time()))}",
                            'entry_price': estado.get('entry_price', 0.0),
                            'amount': estado.get('amount', 0.0),
                            'dca_level': estado.get('dca_level', 0),
                            'total_invested': estado.get('total_invested', 0.0),
                            'entry_time': estado.get('entry_time', 0.0),
                            'entry_mode': estado.get('entry_mode', ''),
                        })
                    estado['positions'] = positions
                    # Limpiar campos viejos
                    for key in ['in_position', 'entry_price', 'amount', 'dca_level',
                                'total_invested', 'entry_time', 'entry_mode',
                                'dca_ejecutado', 'stop_loss', 'take_profit',
                                'scalp_sl', 'swing_tp', 'last_scalp_attempt_time',
                                'last_stop_loss_time', 'trade_mode',
                                'dynamic_tp_activation', 'trailing_active',
                                'highest_price']:
                        estado.pop(key, None)
                    print("🔄 Estado migrado a formato multi-posicion")

                # Asegurar que positions existe
                if 'positions' not in estado:
                    estado['positions'] = []

                # Reinicio diario
                hoy = datetime.now().strftime('%Y-%m-%d')
                if estado.get('last_updated_date') != hoy:
                    estado['last_updated_date'] = hoy
                    estado['daily_start_balance'] = 0

                # Campos de tracking acumulado (se agregan una sola vez)
                if 'capital_inicial' not in estado:
                    estado['capital_inicial'] = 0
                if 'total_pnl' not in estado:
                    estado['total_pnl'] = 0.0
                if 'total_fees' not in estado:
                    estado['total_fees'] = 0.0
                if 'total_trades' not in estado:
                    estado['total_trades'] = 0

                return estado

        except Exception as e:
            print(f"⚠️ Error cargando estado: {e}")

    return {
        'positions': [],
        'usdt_disponible': 0.0,
        'daily_start_balance': 0,
        'last_updated_date': datetime.now().strftime('%Y-%m-%d'),
        'trade_history': [],
        'agent_decisions': [],
        'capital_inicial': 0,
        'total_pnl': 0.0,
        'total_fees': 0.0,
        'total_trades': 0,
    }


def guardar_estado(estado):
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(estado, f, indent=4)
    except Exception as e:
        print(f"❌ Error guardando estado: {e}")


def generar_position_id():
    return f"pos_{int(time.time())}"


def get_total_btc_positions(estado):
    return sum(p.get('amount', 0) for p in estado.get('positions', []))


def get_total_invested(estado):
    return sum(p.get('total_invested', 0) for p in estado.get('positions', []))


def has_open_positions(estado):
    return len(estado.get('positions', [])) > 0


def get_position_by_id(estado, pos_id):
    for p in estado.get('positions', []):
        if p.get('id') == pos_id:
            return p
    return None


def remove_position(estado, pos_id):
    estado['positions'] = [p for p in estado.get('positions', []) if p.get('id') != pos_id]


def registrar_decision_agente(estado, decision_source, action, confidence, reasoning):
    if 'agent_decisions' not in estado:
        estado['agent_decisions'] = []
    entry = {
        'timestamp': datetime.now().isoformat(),
        'source': decision_source,
        'action': action,
        'confidence': confidence,
        'reasoning': reasoning[:120],
    }
    estado['agent_decisions'].append(entry)
    estado['agent_decisions'] = estado['agent_decisions'][-20:]


def registrar_trade(estado, action, price, amount, pnl=None, fee=0.0):
    if 'trade_history' not in estado:
        estado['trade_history'] = []
    entry = {
        'timestamp': datetime.now().isoformat(),
        'action': action,
        'price': price,
        'amount': amount,
        'pnl': pnl,
        'fee': fee,
    }
    estado['trade_history'].append(entry)
    estado['trade_history'] = estado['trade_history'][-10:]

    # Acumular PnL y fees totales
    if pnl is not None:
        estado['total_pnl'] = estado.get('total_pnl', 0) + pnl
    estado['total_fees'] = estado.get('total_fees', 0) + fee
    estado['total_trades'] = estado.get('total_trades', 0) + 1


def get_recent_decisions_summary(estado, max_entries=5) -> str:
    """Comprime las ultimas N decisiones del agente para incluir en el prompt LLM."""
    decisions = estado.get('agent_decisions', [])
    if not decisions:
        return ""

    recent = decisions[-max_entries:]
    lines = ["DECISIONES_PREVIAS:"]
    for d in recent:
        ts = d.get('timestamp', '')[-8:-3]  # HH:MM
        act = d.get('action', '?')
        conf = d.get('confidence', 0)
        reason = d.get('reasoning', '')[:50]
        lines.append(f" {ts}|{act}|c:{conf:.2f}|{reason}")
    return "\n".join(lines)


def get_recent_trades_summary(estado) -> str:
    history = estado.get('trade_history', [])
    if not history:
        return "HISTORIAL: Sin trades recientes."

    lines = ["HISTORIAL RECIENTE:"]
    wins = sum(1 for t in history if t.get('pnl') and t['pnl'] > 0)
    losses = sum(1 for t in history if t.get('pnl') and t['pnl'] < 0)
    lines.append(f"  Ultimos {len(history)} trades: {wins} ganados, {losses} perdidos")

    last = history[-1]
    result = "ganado" if last.get('pnl', 0) > 0 else "perdido"
    lines.append(f"  Ultimo: {last['action']} a ${last['price']:.2f} ({result})")

    return "\n".join(lines)
