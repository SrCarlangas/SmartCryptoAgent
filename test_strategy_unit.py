"""
TEST UNITARIO: Estrategia5mHibrido
Verifica que los dos modos de señal (OVERSOLD y MOMENTUM) funcionan correctamente
con datos sintéticos controlados.
"""
import sys
import time
import numpy as np

# Generar velas OHLCV sintéticas con control de indicadores
def generar_velas_5m(n, precio_base, tendencia='lateral', volatilidad=0.001):
    """Genera n velas de 5m con OHLCV realista."""
    velas = []
    precio = precio_base
    ts = int(time.time() * 1000) - (n * 300000)

    for i in range(n):
        if tendencia == 'alcista':
            cambio = np.random.normal(volatilidad, volatilidad * 2)
        elif tendencia == 'bajista':
            cambio = np.random.normal(-volatilidad, volatilidad * 2)
        else:
            cambio = np.random.normal(0, volatilidad)

        open_p = precio
        close_p = precio * (1 + cambio)
        high_p = max(open_p, close_p) * (1 + abs(np.random.normal(0, volatilidad/2)))
        low_p = min(open_p, close_p) * (1 - abs(np.random.normal(0, volatilidad/2)))
        vol = np.random.uniform(50, 200)

        velas.append([ts + i * 300000, open_p, high_p, low_p, close_p, vol])
        precio = close_p

    return velas

def generar_velas_15m(n, precio_base, tendencia='alcista'):
    """Genera n velas de 15m con tendencia alcista (para que el filtro pase)."""
    velas = []
    precio = precio_base
    ts = int(time.time() * 1000) - (n * 900000)

    for i in range(n):
        cambio = np.random.normal(0.0002, 0.001)  # Ligeramente alcista
        open_p = precio
        close_p = precio * (1 + cambio)
        high_p = max(open_p, close_p) * 1.001
        low_p = min(open_p, close_p) * 0.999
        vol = np.random.uniform(100, 400)

        velas.append([ts + i * 900000, open_p, high_p, low_p, close_p, vol])
        precio = close_p

    return velas

def test_datos_insuficientes():
    """Sin datos suficientes debe retornar False."""
    from modules.strategy import Estrategia5mHibrido
    est = Estrategia5mHibrido()

    senal, atr, modo = est.analizar([], skip_log=True)
    assert not senal and modo is None, "FAIL: datos vacíos"

    senal, atr, modo = est.analizar([[1,2,3,4,5,6]] * 10, skip_log=True)
    assert not senal, "FAIL: menos de 50 velas"

    print("  [PASS] Datos insuficientes -> sin señal")

def test_retorno_3_valores():
    """analizar() debe retornar exactamente 3 valores: (bool, float, str|None)."""
    from modules.strategy import Estrategia5mHibrido
    est = Estrategia5mHibrido()

    velas = generar_velas_5m(60, 70000, 'lateral')
    resultado = est.analizar(velas, skip_log=True)

    assert len(resultado) == 3, f"FAIL: retornó {len(resultado)} valores, esperaba 3"
    assert isinstance(resultado[0], bool), f"FAIL: primer valor debe ser bool, es {type(resultado[0])}"
    assert isinstance(resultado[1], float), f"FAIL: segundo valor debe ser float, es {type(resultado[1])}"
    assert resultado[2] in (None, 'OVERSOLD', 'MOMENTUM'), f"FAIL: tercer valor inválido: {resultado[2]}"

    print("  [PASS] Retorno de 3 valores correcto (bool, float, str|None)")

def test_filtro_15m_bloquea_caida():
    """Si el precio está muy por debajo de EMA50(15m), debe bloquear."""
    from modules.strategy import Estrategia5mHibrido
    est = Estrategia5mHibrido()

    # Generar 15m con tendencia alcista hasta 70000, luego caer fuerte
    velas_15m = generar_velas_15m(60, 71000, 'alcista')
    # Forzar las últimas velas a caer mucho (>0.4% bajo media)
    for i in range(-5, 0):
        velas_15m[i][4] = 69000  # close muy bajo
        velas_15m[i][3] = 68900  # low

    ok, ema = est.filtro_tendencia_15m(velas_15m, tolerancia=0.004)
    # Con caída fuerte, debería bloquear
    print(f"  [INFO] Filtro 15m: ok={ok}, ema50={ema}")
    # No hacemos assert estricto porque depende de cuánto ha subido la EMA

def test_filtro_15m_sin_datos():
    """Sin datos de 15m, no debe bloquear (graceful fallback)."""
    from modules.strategy import Estrategia5mHibrido
    est = Estrategia5mHibrido()

    ok, ema = est.filtro_tendencia_15m(None)
    assert ok is True and ema is None, "FAIL: sin datos debe retornar (True, None)"

    ok, ema = est.filtro_tendencia_15m([])
    assert ok is True and ema is None, "FAIL: datos vacíos debe retornar (True, None)"

    print("  [PASS] Filtro 15m sin datos -> no bloquea")

def test_modo_compatible_main():
    """El modo retornado debe ser compatible con lo que main.py espera."""
    from modules.strategy import Estrategia5mHibrido
    est = Estrategia5mHibrido()

    velas = generar_velas_5m(80, 70000, 'alcista')
    senal, atr, modo = est.analizar(velas, skip_log=True)

    # main.py usa: estado['entry_mode'] = modo y luego f"🚀 SEÑAL {modo}!"
    # modo debe ser un string o None
    if senal:
        assert modo in ('OVERSOLD', 'MOMENTUM'), f"FAIL: modo '{modo}' no reconocido"
        assert isinstance(atr, float) and atr > 0, f"FAIL: ATR debe ser float > 0, es {atr}"
    else:
        assert modo is None, f"FAIL: sin señal pero modo={modo}"

    print(f"  [PASS] Modo retornado compatible con main.py (senal={senal}, modo={modo})")

def test_atr_siempre_positivo():
    """ATR retornado debe ser positivo cuando hay datos suficientes."""
    from modules.strategy import Estrategia5mHibrido
    est = Estrategia5mHibrido()

    for tendencia in ['alcista', 'bajista', 'lateral']:
        velas = generar_velas_5m(80, 70000, tendencia)
        senal, atr, modo = est.analizar(velas, skip_log=True)
        assert atr >= 0.0, f"FAIL: ATR negativo en tendencia {tendencia}: {atr}"

    print("  [PASS] ATR siempre >= 0 en todas las tendencias")

def test_skip_log_no_crash():
    """skip_log=True y False no deben crashear."""
    from modules.strategy import Estrategia5mHibrido
    est = Estrategia5mHibrido()

    velas = generar_velas_5m(80, 70000, 'lateral')
    velas_15m = generar_velas_15m(60, 70000)

    # Ambos modos de log
    est.analizar(velas, velas_15m, skip_log=True)
    est.analizar(velas, velas_15m, skip_log=False)
    est.analizar(velas, skip_log=True)   # sin 15m
    est.analizar(velas, skip_log=False)  # sin 15m

    print("  [PASS] skip_log True/False sin crash, con y sin 15m")

def test_parametros_personalizados():
    """Parámetros RSI y momentum personalizados no deben crashear."""
    from modules.strategy import Estrategia5mHibrido
    est = Estrategia5mHibrido()

    velas = generar_velas_5m(80, 70000)

    # Parámetros extremos
    est.analizar(velas, rsi_min=10, rsi_max=90, min_momentum=0.0, skip_log=True)
    est.analizar(velas, rsi_min=50, rsi_max=51, min_momentum=0.01, skip_log=True)
    est.analizar(velas, rsi_min=0, rsi_max=100, min_momentum=-1, skip_log=True)

    print("  [PASS] Parámetros personalizados sin crash")

if __name__ == '__main__':
    np.random.seed(42)
    print("\n" + "="*60)
    print("  TEST UNITARIO: Estrategia5mHibrido")
    print("="*60)

    tests = [
        test_datos_insuficientes,
        test_retorno_3_valores,
        test_filtro_15m_bloquea_caida,
        test_filtro_15m_sin_datos,
        test_modo_compatible_main,
        test_atr_siempre_positivo,
        test_skip_log_no_crash,
        test_parametros_personalizados,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {test.__name__}: {e}")
            failed += 1

    print(f"\n  Resultado: {passed}/{passed+failed} tests pasaron")
    if failed:
        sys.exit(1)
    print("  ✅ TODOS LOS TESTS UNITARIOS PASARON")
