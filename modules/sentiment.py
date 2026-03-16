import requests
from modules.logger import logger

class NewsAnalyzer:
    def __init__(self):
        # API pública de Alternative.me (No requiere Token)
        self.url = "https://api.alternative.me/fng/"

    def obtener_sentimiento(self):
        """
        Retorna un valor normalizado entre -1 (Miedo Extremo) y 1 (Codicia Extrema)
        para mantener compatibilidad con la lógica de nuestro bot.
        """
        try:
            response = requests.get(self.url, timeout=10).json()
            data = response.get('data', [])
            
            if not data: return 0

            # El índice viene de 0 a 100
            # 0 = Miedo Extremo (Bearish)
            # 100 = Codicia Extrema (Bullish)
            valor_fng = int(data[0]['value'])
            
            # Convertimos de escala 0-100 a escala -1 a 1
            # Fórmula: (valor - 50) / 50
            score_normalizado = (valor_fng - 50) / 50
            
            # Log para depuración
            estado = data[0]['value_classification']
            logger.info(f"🧠 SENTIMIENTO MERCADO: {valor_fng}/100 ({estado}) -> Score: {score_normalizado:.2f}")
            
            return score_normalizado

        except Exception as e:
            logger.error(f"Error obteniendo Fear & Greed Index: {e}")
            return 0 # Neutral por defecto