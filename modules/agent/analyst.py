import json
import re
import time
from modules.agent.models import MarketContext, TradingDecision
from modules.agent.prompts import SYSTEM_PROMPT, RESPONSE_SCHEMA, build_analysis_prompt
from modules.logger import logger
from config import (
    GOOGLE_API_KEY, AGENT_MODEL, AGENT_CALL_TIMEOUT,
    AGENT_MAX_OUTPUT_TOKENS,
)


class MarketAnalyst:
    """Agente validador que usa Gemini para confirmar/ajustar decisiones pre-calculadas."""

    MAX_RETRIES = 2
    RETRY_BACKOFF = [2, 5]

    def __init__(self):
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            from google import genai
            self._client = genai.Client(api_key=GOOGLE_API_KEY)

    def analyze(self, ctx: MarketContext, rules_recommendation: TradingDecision = None,
                timeout: float = AGENT_CALL_TIMEOUT) -> TradingDecision:
        """Valida/ajusta la recomendacion pre-calculada usando el LLM."""
        self._ensure_client()

        prompt = build_analysis_prompt(ctx, rules_recommendation)
        decision = TradingDecision(source="agent")

        for attempt in range(self.MAX_RETRIES):
            try:
                start = time.time()

                config = {
                    "system_instruction": SYSTEM_PROMPT,
                    "response_mime_type": "application/json",
                    "response_schema": RESPONSE_SCHEMA,
                    "temperature": 0.3,
                    "max_output_tokens": AGENT_MAX_OUTPUT_TOKENS,
                }

                response = self._client.models.generate_content(
                    model=AGENT_MODEL,
                    contents=prompt,
                    config=config,
                )
                elapsed = time.time() - start

                self._log_token_usage(response, elapsed)

                raw_text = response.text
                if not raw_text:
                    logger.warning(f"Agente retorno respuesta vacia (intento {attempt+1}/{self.MAX_RETRIES})")
                    if attempt < self.MAX_RETRIES - 1:
                        time.sleep(self.RETRY_BACKOFF[attempt])
                    continue

                data = self._parse_json(raw_text)

                # LLM devuelve 3 campos: action, confidence, risk
                llm_action = data.get("action", "HOLD")
                llm_confidence = float(data.get("confidence", 0.0))
                llm_risk = data.get("risk", "medium")

                # Reasoning: reglas aportan contexto, LLM aporta la decision
                llm_reasoning = rules_recommendation.reasoning if rules_recommendation else ""

                # Construir decision del agente
                decision.action = llm_action
                decision.confidence = llm_confidence
                decision.reasoning = llm_reasoning
                decision.risk_assessment = llm_risk
                decision.market_regime = ctx.regime

                # Auto-seleccionar position si el LLM no hereda de reglas
                if llm_action in ("SELL", "DCA", "PARTIAL_SELL") and not decision.target_position_id:
                    decision.target_position_id = self._auto_select_position(ctx, llm_action)
                if llm_action == "BUY" and not decision.suggested_allocation_pct:
                    decision.suggested_allocation_pct = 0.05  # default conservador

                logger.info(
                    f"AGENTE [{elapsed:.1f}s]: {decision.action} "
                    f"[{decision.target_position_id}] "
                    f"(conf:{decision.confidence:.2f}) | {decision.reasoning}"
                )
                return decision

            except json.JSONDecodeError as e:
                logger.warning(f"JSON invalido del agente (intento {attempt+1}/{self.MAX_RETRIES}): {e}")
            except Exception as e:
                logger.warning(f"Error agente (intento {attempt+1}/{self.MAX_RETRIES}): {e}")

            if attempt < self.MAX_RETRIES - 1:
                wait = self.RETRY_BACKOFF[attempt]
                logger.info(f"Reintentando agente en {wait}s...")
                time.sleep(wait)

        # Fallback: si el LLM falla, usar la recomendacion pre-calculada directamente
        if rules_recommendation and rules_recommendation.action != "HOLD":
            logger.warning(f"Agente fallo despues de {self.MAX_RETRIES} intentos. Usando recomendacion de reglas.")
            rules_recommendation.source = "rules_llm_failure"
            return rules_recommendation

        logger.warning(f"Agente fallo despues de {self.MAX_RETRIES} intentos. Retornando HOLD.")
        decision.action = "HOLD"
        decision.confidence = 0.0
        decision.reasoning = "Error en agente, fallback a HOLD"
        decision.source = "rules_api_failure"
        return decision

    def _parse_json(self, raw_text):
        """Extrae y parsea JSON de la respuesta del LLM de forma robusta."""
        # 1. Intento directo
        try:
            return json.loads(raw_text)
        except json.JSONDecodeError:
            pass

        # 2. Extraer bloque JSON con regex
        match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', raw_text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        # 3. Limpiar markdown y reintentar
        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r'^```\w*\n?', '', cleaned)
            cleaned = re.sub(r'\n?```$', '', cleaned)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # 4. Log del texto raw para diagnostico y re-raise
        logger.warning(f"Raw LLM response (no JSON): {raw_text[:300]}")
        raise json.JSONDecodeError("No se pudo extraer JSON valido", raw_text, 0)

    def _log_token_usage(self, response, elapsed):
        """Log de uso de tokens para monitoreo de costos."""
        try:
            usage = response.usage_metadata
            if not usage:
                return
            input_tokens = getattr(usage, 'prompt_token_count', 0) or 0
            output_tokens = getattr(usage, 'candidates_token_count', 0) or 0
            logger.info(
                f"Tokens: in={input_tokens} out={output_tokens} | {elapsed:.1f}s"
            )
        except Exception:
            pass

    def _auto_select_position(self, ctx, action):
        """Si el agente no especifico position_id, seleccionar la mas logica."""
        if not ctx.positions:
            return ""
        if action in ("SELL", "PARTIAL_SELL"):
            best = max(ctx.positions, key=lambda p: p.roi_current)
            return best.id
        if action == "DCA":
            candidates = [p for p in ctx.positions if p.dca_level < 2]
            if candidates:
                worst = min(candidates, key=lambda p: p.roi_current)
                return worst.id
        return ""
