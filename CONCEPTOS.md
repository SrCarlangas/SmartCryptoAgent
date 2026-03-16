# Bot de Trading BTC/USDT — Arquitectura Avanzada (Smart DCA Multi-Step)

## Flujo Principal (15 Minutos + Micro-Rebotes de 1m)

```mermaid
graph TD
    A[Monitor de Precio y Saldo] --> B{¿Posición Abierta?}
    B -- NO --> C{Analizar Sentimiento (Fear & Greed)}
    C -- PÁNICO ABSOLUTO (< -0.95) --> D[Congelar Compras]
    C -- NORMAL/GREED/MIEDO (>= -0.95) --> E[Evaluar Estrategia 15m]
    E -- Señal Confirmada --> F[COMPRA BASE (aprox 15% del Portafolio total)]
    
    B -- SÍ --> G{Evaluar Rendimiento (ROI)}
    G -- "Cae al Umbral DCA (-1.5%, -3%, -4.5%)" --> H[Armar Rescate y Esperar]
    H -- "Confirma micro-rebote de RSI de 1 minuto" --> I[COMPRA DCA Nivel Correspondiente]
    I --> J(Promedia el Precio de Entrada Masivamente)
    
    G -- "Supera el +[TP Dinámico %]" --> K[Activar Trailing Stop]
    K --> L("Persigue el precio máximo")
    L -- "Cae -0.5% desde el pico" --> M[VENTA (Toma de Ganancias)]
    
    G -- "Cae al -2.5%" --> N[VENTA (Stop Loss Catastrófico)]
```

---

## Estrategia Funcional: Multi-Step DCA con Trailing Dinámico

El bot ha sido actualizado a un sistema de **Dollar Cost Averaging Inteligente de 3 Balas** y cuenta con objetivos de ganancia flexibles de acuerdo a la volatilidad del momento.

| Parámetro | Configuración |
|---|---|
| **Capital Máximo a usar (Exposure)** | 60% de tu balance real (protegiendo el otro 40%) |
| **Filtro de Pánico** | Bloqueo solo con apocalipsis total (`< -0.95`). Miedo común (`< -0.80`) no detiene el bot. |
| **Grilla DCA (Multi-Step)** | Dispara 3 rescates fraccionados a `-1.5%`, `-3.0%` y `-4.5%`. |
| **Trailing DCA (Anti Cuchillos)**| Al tocar un piso de la grilla, **NO compra** ciegamente. Espera que la fuerza de venta pare (RSI de 1 minuto revirtiendo tendencia en sobreventa). |
| **Take Profit Dinámico (ATR)**| El Trailing ya no se activa al aburrido +1.5%. Se activa adaptativamente basándose en la volatilidad actual (`ATR * 1.5 Multiplicador`). ¡Gana más cuando el mercado es violento! |
| **Stop Loss Catastrófico** | `-2.5%` de caída desde el precio promedio final. Corta pérdidas masivas. |

---

## Cómo se Reparte tu Portafolio ("Las 4 Balas")

En lugar de arriesgar todo en un solo precio o hacer un DCA 50/50 estúpido, el bot entra de forma escalonada con una arquitectura diseñada para reventar el precio promedio hacia abajo al final de la caída de Bitcoin:

*   **Entrada Base:** Compra el 25% del capital asignado.
*   **DCA Nivel 1 (-1.5%):** Compra el 15% del capital (ligero primer rebote).
*   **DCA Nivel 2 (-3.0%):** Compra el 25% del capital.
*   **DCA Nivel 3 (-4.5%):** Compra el 35% del capital (Aplastando el precio de entrada a niveles rentables casi de inmediato para un rebote veloz).

---

## Toma de Beneficios (Trailing Stop Adaptativo)

El bot **NO** vende al tocar un número fijo. Y **NO** activa el Trailing en un número fijo. ¡Es inteligente!
1. Calcula la meta basada en: `ATR Actual * 1.5 Multiplicador`.
2. Si el mercado está aburrido, la meta es pequeña para asegurar algo. Si el mercado está en un mega-rally alcista, la meta crece exponencialmente.
3. Al tocar esa Meta Dinámica, bloquea las ganancias y enciende el *Trailing*.
4. Sólo venderá cuando el precio se debilite y caiga un **-0.5%** desde el pico histórico de esa ola de ganancias.
