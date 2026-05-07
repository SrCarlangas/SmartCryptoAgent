"""Parser de instrucciones en lenguaje natural.

M1: stub básico con detección regex para los patrones más comunes.
M4: integración con Gemini para casos complejos.
"""
import re
from typing import List, Optional, Tuple

from modules.instructions.models import Action, Condition, Instruction


# ---------- Regex helpers (patrones comunes en español/inglés) ----------
# Precio: número entero o decimal con punto, opcional sufijo 'k', opcional '$'
_PRICE_RE = r"\$?\s*([\d]+(?:\.\d+)?[k]?)"
_BTC_QTY_RE = r"([\d]+(?:\.\d+)?)\s*btc"


def _norm_number(s: str) -> float:
    s = s.strip().lower().replace(",", "")
    mult = 1.0
    if s.endswith("k"):
        mult = 1000.0
        s = s[:-1]
    try:
        return float(s) * mult
    except Exception:
        return 0.0


_BELOW_KEYWORDS = ("baj", "cae", "caer", "drop", "debajo", "menor", "<=", "<", "menos")
_ABOVE_KEYWORDS = ("sub", "rise", "supera", "encima", "mayor", ">=", ">",
                   "alcanc", "lleg", "reach", "hit")
# Triggers que separan "qué hago" de "cuándo lo hago"
_CONDITION_TRIGGERS = ("si ", " si", "cuando", "when", "if ")


def _has_keyword(text: str, kws) -> bool:
    t = text.lower()
    return any(kw in t for kw in kws)


def _find_price_after(text: str, keywords) -> Optional[float]:
    """Busca el primer número (precio) que aparece después de cualquiera de los keywords."""
    t = text.lower()
    earliest_kw = None
    earliest_pos = len(text)
    for kw in keywords:
        idx = t.find(kw)
        if idx >= 0 and idx < earliest_pos:
            earliest_kw = kw
            earliest_pos = idx
    if earliest_kw is None:
        return None
    # Buscar el primer número después del keyword
    after = text[earliest_pos + len(earliest_kw):]
    m = re.search(_PRICE_RE, after, re.IGNORECASE)
    if not m:
        return None
    return _norm_number(m.group(1))


def _detect_clause_condition(clause: str, is_buy: bool) -> Optional[Condition]:
    """Dado un clause de compra/venta, detecta su condición de precio."""
    # Detectar dirección
    has_below = _has_keyword(clause, _BELOW_KEYWORDS)
    has_above = _has_keyword(clause, _ABOVE_KEYWORDS)

    if has_below and not has_above:
        price = _find_price_after(clause, _BELOW_KEYWORDS)
        if price and price > 0:
            return Condition(type="price_below", value=price, operator="<=")
    if has_above and not has_below:
        price = _find_price_after(clause, _ABOVE_KEYWORDS)
        if price and price > 0:
            return Condition(type="price_above", value=price, operator=">=")
    if has_below and has_above:
        # Ambos presentes: priorizar el que aparezca primero en el texto
        below_pos = min((clause.lower().find(k) for k in _BELOW_KEYWORDS if k in clause.lower()), default=999)
        above_pos = min((clause.lower().find(k) for k in _ABOVE_KEYWORDS if k in clause.lower()), default=999)
        if below_pos < above_pos:
            price = _find_price_after(clause, _BELOW_KEYWORDS)
            if price and price > 0:
                return Condition(type="price_below", value=price, operator="<=")
        else:
            price = _find_price_after(clause, _ABOVE_KEYWORDS)
            if price and price > 0:
                return Condition(type="price_above", value=price, operator=">=")
    return None


def _split_action_from_condition(clause: str) -> str:
    """Devuelve solo la parte 'qué hago' de un clause (lo que está antes del trigger 'si/cuando/when').
    Si el trigger está al inicio del clause (orden invertido tipo 'si X compra Y'),
    devuelve la parte DESPUÉS del trigger en lugar de un string vacío."""
    t = clause.lower()
    earliest = len(clause)
    earliest_kw = ""
    for trig in _CONDITION_TRIGGERS:
        idx = t.find(trig)
        if idx >= 0 and idx < earliest:
            earliest = idx
            earliest_kw = trig
    if earliest >= len(clause):
        return clause
    if earliest == 0:
        # Trigger al inicio (ej: "Si BTC baja a $80000 compra 0.001 BTC")
        # → la parte de acción está DESPUÉS del trigger; la condición está al inicio
        # Devolvemos la cláusula completa para que la cantidad se busque global
        return clause
    return clause[:earliest]


def _detect_quantity(text: str) -> Tuple[float, float]:
    """Retorna (qty_btc, qty_usdt) detectados.

    BTC qty (ej: "0.001 BTC") es muy específico → buscar en cláusula completa.
    USDT explícito ("50 USDT") también es específico → buscar global.
    "$X" solo (ambiguo, puede ser precio gatillo) → solo buscar en parte de acción.
    """
    head = _split_action_from_condition(text)
    qty_btc = 0.0
    qty_usdt = 0.0
    # Búsqueda global: BTC explícito y USDT explícito son patrones inequívocos
    m = re.search(_BTC_QTY_RE, text, re.IGNORECASE)
    if m:
        qty_btc = _norm_number(m.group(1))
    m = re.search(r"([\d]+(?:\.\d+)?)\s*usdt?\b", text, re.IGNORECASE)
    if m:
        qty_usdt = _norm_number(m.group(1))
    # Búsqueda local: $X es ambiguo (puede ser precio gatillo); solo en prefix de acción
    if not qty_btc and not qty_usdt:
        m = re.search(r"\$\s*([\d]+(?:\.\d+)?[k]?)", head)
        if m:
            qty_usdt = _norm_number(m.group(1))
    return qty_btc, qty_usdt


def _split_buy_sell_clauses(text: str) -> Tuple[str, str]:
    """Divide el texto en cláusula de compra y de venta. Retorna ('', '') si no detecta."""
    txt = text.lower()
    has_buy = "compra" in txt or "buy" in txt
    has_sell = "vende" in txt or "sell" in txt or "venta" in txt

    if not (has_buy or has_sell):
        return "", ""

    # Dividir por conectores: coma, " y ", "then", "luego", "despues"
    parts = re.split(
        r",\s*|\s+y\s+|\s+then\s+|\s+luego\s+|\s+despu[eé]s\s+",
        text,
        flags=re.IGNORECASE,
    )
    buy_text = ""
    sell_text = ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        p = part.lower()
        if ("compra" in p or "buy" in p) and not buy_text:
            buy_text = part
        elif ("vende" in p or "sell" in p or "venta" in p) and not sell_text:
            sell_text = part
        elif buy_text and not sell_text:
            # Cláusulas continuación pueden no repetir el verbo (ej: "y vende a $X" → "a $X")
            # Si ya tenemos compra y este part tiene una condición de precio sola, asumimos venta
            if re.search(_PRICE_RE, part):
                sell_text = part
    return buy_text, sell_text


def parse_instruction(text: str, complex_mode: bool = False) -> Instruction:
    """Parser regex. Si no se puede extraer estructura, marca como `complex` con warnings."""
    inst = Instruction(raw_text=text.strip(), complex=complex_mode)
    warnings: List[str] = []

    if complex_mode or not text.strip():
        warnings.append(
            "Modo complejo: la instrucción se evaluará con LLM cada ciclo "
            "(integración LLM aún no disponible — instrucción no podrá activarse)."
        )
        inst.parse_warnings = warnings
        return inst

    buy_clause, sell_clause = _split_buy_sell_clauses(text)
    qty_btc, qty_usdt = _detect_quantity(buy_clause or text)

    # Caso 1: solo compra ("compra X BTC si baja a Y")
    if buy_clause and not sell_clause:
        cond = _detect_clause_condition(buy_clause, is_buy=True)
        if cond and (qty_btc > 0 or qty_usdt > 0):
            inst.entry_conditions = [cond]
            inst.entry_action = Action(
                type="BUY", quantity_btc=qty_btc, quantity_usdt=qty_usdt
            )
        else:
            if not cond:
                warnings.append("No pude extraer la condición de precio para la compra.")
            if qty_btc <= 0 and qty_usdt <= 0:
                warnings.append("No pude extraer la cantidad (BTC o USDT) para la compra.")

    # Caso 2: solo venta ("vende cuando suba a X")
    elif sell_clause and not buy_clause:
        cond = _detect_clause_condition(sell_clause, is_buy=False)
        if cond:
            inst.entry_conditions = [cond]  # entry = venta inmediata cuando se cumpla
            inst.entry_action = Action(
                type="SELL", sell_pct=1.0, target_position_id="any"
            )
        else:
            warnings.append("No pude extraer la condición de precio para la venta.")

    # Caso 3: compra + venta combinada
    elif buy_clause and sell_clause:
        buy_cond = _detect_clause_condition(buy_clause, is_buy=True)
        sell_cond = _detect_clause_condition(sell_clause, is_buy=False)

        if buy_cond and (qty_btc > 0 or qty_usdt > 0):
            inst.entry_conditions = [buy_cond]
            inst.entry_action = Action(
                type="BUY", quantity_btc=qty_btc, quantity_usdt=qty_usdt
            )
        else:
            if not buy_cond:
                warnings.append("No pude extraer la condición de precio para la compra.")
            if qty_btc <= 0 and qty_usdt <= 0:
                warnings.append("No pude extraer la cantidad (BTC o USDT) para la compra.")

        if sell_cond:
            inst.exit_conditions = [sell_cond]
            inst.exit_action = Action(
                type="SELL", sell_pct=1.0, target_position_id="any"
            )
        else:
            warnings.append("No pude extraer la condición de precio para la venta.")

    else:
        warnings.append(
            "No detecté acción (compra/venta) en la instrucción. "
            "Usa frases como 'compra X BTC si baja a $Y' o 'vende cuando llegue a $Y'."
        )

    if not inst.entry_action and not inst.exit_action:
        warnings.append(
            "Instrucción no parseable — sugerencia: marcar como compleja para evaluación LLM."
        )

    inst.parse_warnings = warnings
    return inst
