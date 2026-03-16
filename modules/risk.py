from modules.logger import logger

class RiskManager:
    def __init__(self, daily_loss_limit=0.03):
        self.daily_loss_limit = daily_loss_limit # Línea de freno de emergencia

    def get_dca_allocations(self, total_balance, max_dca_exposure=0.70):
        """
        Calcula el tamaño de la compra Base y del Rescate DCA para Smart DCA.
        Distribución: Base (10%) + DCA1 (20%) + DCA2 (40%) del budget total.
        Esta distribución permite promediar a la baja de manera ponderada.
        """
        budget_dca = total_balance * max_dca_exposure

        compra_base = budget_dca * 0.10  # 10%
        dca_1 = budget_dca * 0.20        # 20%
        dca_2 = budget_dca * 0.40        # 40%

        return compra_base, dca_1, dca_2

    def verificar_limite_diario(self, current_balance, starting_balance_day):
        """
        Verifica si hemos perdido más del límite diario permitido.
        """
        current_loss_pct = (current_balance - starting_balance_day) / starting_balance_day
        
        if current_loss_pct < -self.daily_loss_limit:
            logger.error(f"🛑 CRÍTICO: Límite de pérdida diaria alcanzado ({current_loss_pct*100:.2f}%). Deteniendo operaciones nuevas.")
            return False # No es seguro operar
            
        return True

    def es_seguro_operar(self, current_balance, starting_balance_day):
        return self.verificar_limite_diario(current_balance, starting_balance_day)

# --- CLASE ACTUALIZADA AL ATR ---
class TrailingStopATR:
    def __init__(self, multiplicador=2.0):
        self.multiplicador = multiplicador
        self.high_price = 0
        self.stop_price = 0
        self.active = False

    def reset(self, entry_price, atr_inicial):
        """Se ejecuta al momento de comprar para fijar el stop inicial"""
        self.high_price = entry_price
        # El stop se coloca por debajo del precio de entrada según la volatilidad
        self.stop_price = entry_price - (atr_inicial * self.multiplicador)
        self.active = True

    def update(self, current_price, current_atr):
        """Se ejecuta en cada ciclo para ver si el stop debe subir o si se tocó"""
        if not self.active:
            return False

        # 1. ¿El precio hizo un nuevo máximo? Actualizamos referencia
        if current_price > self.high_price:
            self.high_price = current_price
            
        # 2. Calcular el nuevo Stop Loss propuesto
        nuevo_stop_propuesto = self.high_price - (current_atr * self.multiplicador)
        
        # Regla de oro: El Trailing Stop SOLO PUEDE SUBIR
        if nuevo_stop_propuesto > self.stop_price:
            self.stop_price = nuevo_stop_propuesto
        
        # 3. ¿El precio actual rompió el Stop? -> SEÑAL DE VENTA
        if current_price <= self.stop_price:
            self.active = False
            return True # Retorna True indicando que hay que vender
            
        return False # Retorna False si aún estamos a salvo