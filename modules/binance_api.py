import ccxt
import os
import time
from dotenv import load_dotenv
from modules.logger import logger

load_dotenv()

class BinanceConnector:
    def __init__(self):
        is_prod = os.getenv('PROD_MODE') == 'True'

        # Inicializamos nuestra conexión principal con las llaves Demo
        self.exchange = ccxt.binance({
            'apiKey': os.getenv('BINANCE_API_KEY'),
            'secret': os.getenv('BINANCE_SECRET'),
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'}
        })

        if not is_prod:
            logger.info("--- 🟢 MODO DEMO GRÁFICO (Clonación Anónima) ---")

            for intento in range(1, 4):
                try:
                    # 1. EL ESPÍA ANÓNIMO
                    logger.info("Descargando mapa del mercado...")
                    espia = ccxt.binance({'enableRateLimit': True})
                    mapa_perfecto = espia.load_markets()

                    # 2. INYECCIÓN DEL MAPA
                    self.exchange.set_markets(mapa_perfecto)
                    self.exchange.markets_loaded = True

                    # 3. EL SECUESTRO DE URLs
                    base_url = 'https://demo-api.binance.com/api/v3'
                    self.exchange.urls['api'] = {
                        'public': base_url,
                        'private': base_url,
                        'v3': base_url,
                        'sapi': 'https://demo-api.binance.com/sapi/v1',
                    }
                    logger.info("Conectado al simulador exitosamente.")
                    break
                except Exception as e:
                    if intento < 3:
                        logger.warning(f"⚠️ Error inicializando Demo (intento {intento}/3): {e}. Reintentando...")
                        time.sleep(2)
                    else:
                        logger.warning(f"⚠️ Error inicializando Demo tras 3 intentos: {e}")

    def _reintentar(self, operacion, *args, max_intentos=3, pausa=2, sin_reintento=None, **kwargs):
        """
        Ejecuta una operación de API con hasta max_intentos reintentos.
        sin_reintento: lista de strings de error que indican rechazo definitivo (no reintentar).
        """
        for intento in range(1, max_intentos + 1):
            try:
                return operacion(*args, **kwargs)
            except Exception as e:
                if sin_reintento and any(s in str(e).lower() for s in sin_reintento):
                    raise  # Error definitivo: no tiene sentido reintentar
                if intento < max_intentos:
                    logger.warning(f"⚠️ Reintento {intento}/{max_intentos - 1}: {e}")
                    time.sleep(pausa)
                else:
                    raise  # Agotar reintentos: re-lanzar para que el caller lo maneje

    def obtener_precio(self, symbol):
        try:
            ticker = self._reintentar(self.exchange.fetch_ticker, symbol)
            return float(ticker['last'])
        except Exception as e:
            logger.warning(f"⚠️ Error leyendo precio: {e}")
            return None

    def crear_orden(self, symbol, side, amount):
        try:
            order = self._reintentar(
                self.exchange.create_order, symbol, 'market', side, amount,
                sin_reintento=['insufficient balance']  # Rechazo definitivo, no reintentar
            )
            modo = "REAL" if os.getenv('PROD_MODE') == 'True' else "DEMO"
            logger.info(f"✅ ORDEN ENVIADA [{modo}]: {side.upper()} {amount} {symbol}")
            return order
        except Exception as e:
            logger.error(f"❌ Error creando orden: {e}")
            return None

    def obtener_saldo_btc(self):
        try:
            cuenta = self._reintentar(self.exchange.private_get_account)
            for asset in cuenta['balances']:
                if asset['asset'] == 'BTC':
                    return float(asset['free'])
            return 0.0  # Si no existe el asset, el saldo es 0
        except Exception as e:
            logger.warning(f"⚠️ Error obteniendo saldo BTC: {e}")
            return None

    def obtener_saldo_usdt(self):
        try:
            cuenta = self._reintentar(self.exchange.private_get_account)
            for asset in cuenta['balances']:
                if asset['asset'] == 'USDT':
                    return float(asset['free'])
            return 0.0
        except Exception as e:
            logger.warning(f"⚠️ Error obteniendo saldo USDT: {e}")
            return None

    def obtener_velas(self, symbol, timeframe='1h', limit=200):
        """Descarga el historial de precios (OHLCV) necesario para los indicadores"""
        try:
            velas = self._reintentar(
                self.exchange.fetch_ohlcv, symbol, timeframe, limit=limit
            )
            return velas
        except Exception as e:
            logger.warning(f"⚠️ Error obteniendo velas: {e}")
            return None
