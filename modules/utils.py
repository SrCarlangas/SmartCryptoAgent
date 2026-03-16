import json
import os
from datetime import datetime

STATE_FILE = 'bot_state.json'

def cargar_estado():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                estado = json.load(f)
                
                # REINICIO DIARIO DE BALANCE (Si cambia el día, reseteamos el balance inicial)
                hoy = datetime.now().strftime('%Y-%m-%d')
                if estado.get('last_updated_date') != hoy:
                     estado['last_updated_date'] = hoy
                     # Se actualizará en el ciclo principal con el balance real
                     estado['daily_start_balance'] = 0 
                return estado
                
        except Exception as e:
            print(f"⚠️ Error cargando estado: {e}")
    
    # Estado inicial por defecto
    return {
        'in_position': False,
        'entry_price': 0.0,
        'amount': 0.0,
        'stop_loss': 0.0,
        'daily_start_balance': 0,
        'last_updated_date': datetime.now().strftime('%Y-%m-%d'),
        'last_stop_loss_time': 0,
        'trade_mode': 'swing',          # 'swing' o 'scalp'
        'take_profit': 0.0,             # Precio TP para modo scalp
        'scalp_sl': 0.0,                # Precio SL para modo scalp
        'swing_tp': 0.0,                # Precio TP para modo swing (+0.5%)
        'entry_time': 0.0,              # Timestamp de entrada (para timeout)
        'usdt_disponible': 0.0,         # Capital USDT rastreado manualmente (anti-bug API Demo)
        'last_scalp_attempt_time': 0,   # Anti-spam: timestamp del último intento de scalp
        'dca_ejecutado': False,         # Control de DCA: solo 1 DCA por posición
    }

def guardar_estado(estado):
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(estado, f, indent=4)
    except Exception as e:
        print(f"❌ Error guardando estado: {e}")