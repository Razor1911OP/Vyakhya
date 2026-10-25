"""
Vyakhya Detection Engine
Complete in-process pipeline: validate → text → txn → context → fusion → tier
"""
import time
from typing import Tuple
from backend.app.schemas import (
    ScoreRequest, ScoreResponse, TierEnum, ReasonCode, ModelVersion, RedactedText
)
from backend.app.core.config import settings
from backend.app.core.logging import get_logger

# Import engine components
from backend.app.engine.validate_redact import validate_and_redact
from backend.app.engine.text_model import get_text_model
from backend.app.engine.txn_model import get_txn_model
from backend.app.engine.context_rules import get_context_engine
from backend.app.engine.fusion import get_fusion_model
from backend.app.engine.tier_policy import get_tier_policy

logger = get_logger(__name__)


class DetectionEngine:
    """
    Main detection engine orchestrator
    Latency budget: < 300ms p95
    """
    
    def __init__(self):
        # Load all models at initialization (warm start)
        logger.info("Initializing detection engine...")
        self.text_model = get_text_model()
        self.txn_model = get_txn_model()
        self.context_engine = get_context_engine()
        self.fusion_model = get_fusion_model()
        self.tier_policy = get_tier_policy()
        logger.info("Detection engine initialized successfully")
    
    def score(self, request: ScoreRequest) -> ScoreResponse:
        """
        Score a payment request and return risk assessment
        
        Pipeline:
        1. Validate + redact
        2. Text model (HF primary, TF-IDF fallback)
        3. Transaction model (XGBoost)
        4. Context rules
        5. Fusion (weighted or trained)
        6. Tier assignment + friction policy
        
        Args:
            request: Score request with message, transaction, context
        
        Returns:
            ScoreResponse with risk score, tier, reasons, friction
        """
        start_time = time.perf_counter()
        
        # Step 1: Validate and redact.
        # full_redacted is in-memory only (scored, never persisted or logged).
        redacted_input, full_redacted = validate_and_redact(request.message_text)
        
        # Step 2: Text model (only if message provided)
        text_prob = 0.0
        text_model_used = "none"
        text_latency = 0
        
        if redacted_input:
            # Score the full redacted text, not the 100-char UI preview
            text_prob, text_model_used, text_latency = self.text_model.predict(full_redacted)
        
        # Step 3: Transaction model
        txn_prob, txn_latency = self.txn_model.predict(request.transaction)
        
        # Step 4: Context rules
        context_score, context_reasons = self.context_engine.compute_context_score(
            request.context, request.transaction
        )
        
        # Step 5: Fusion
        uncalibrated_prob, risk_score_float = self.fusion_model.fuse(
            text_prob, txn_prob, context_score
        )
        risk_score = int(risk_score_float)
        
        # Step 6: Tier assignment
        tier = self.tier_policy.assign_tier(risk_score)
        soft_hold = self.tier_policy.should_soft_hold(tier)
        
        # Compile reason codes (start with context reasons, add more as needed)
        all_reasons = list(context_reasons)
        
        # Add text-based reasons if high text probability
        if text_prob > 0.7:
            all_reasons.insert(0, ReasonCode(
                code="scam_language_detected",
                explanation="Message contains language patterns commonly used in scams",
                confidence=text_prob
            ))
        
        # Add transaction-based reasons if high txn probability
        if txn_prob > 0.7:
            all_reasons.insert(0, ReasonCode(
                code="suspicious_transaction_pattern",
                explanation="Transaction shows patterns associated with fraud",
                confidence=txn_prob
            ))
        
        # Ensure at least one reason code
        if not all_reasons:
            all_reasons.append(ReasonCode(
                code="routine_check",
                explanation="Routine security verification",
                confidence=0.5
            ))
        
        # Limit to top 5 reasons, sorted by confidence
        all_reasons.sort(key=lambda r: r.confidence, reverse=True)
        top_reasons = all_reasons[:5]
        
        # Get friction config
        friction_type, friction_message = self.tier_policy.get_friction_config(tier, top_reasons)
        
        # Calculate total latency
        total_latency_ms = int((time.perf_counter() - start_time) * 1000)
        
        # Build model versions list
        model_versions = [
            ModelVersion(
                model_name=text_model_used,
                version="v1",
                used=(text_model_used != "none")
            ),
            ModelVersion(
                model_name="xgboost_txn",
                version="v1",
                used=True
            ),
            ModelVersion(
                model_name="fusion",
                version="v1",
                used=True
            )
        ]
        
        # Log decision (no raw text)
        logger.info("Payment scored", extra={
            'user_id': request.user_id,
            'risk_score': risk_score,
            'tier': tier.value,
            'soft_hold': soft_hold,
            'latency_ms': total_latency_ms,
            'text_model': text_model_used,
            'simulated_context': request.context.simulated
        })
        
        # Check latency budget
        if total_latency_ms > settings.score_latency_budget_ms:
            logger.warning(f"Latency budget exceeded: {total_latency_ms}ms > {settings.score_latency_budget_ms}ms")
        
        # Build response
        response = ScoreResponse(
            risk_score=risk_score,
            tier=tier,
            soft_hold=soft_hold,
            reason_codes=top_reasons,
            model_versions=model_versions,
            latency_ms=total_latency_ms,
            component_scores={
                'text_prob': text_prob,
                'txn_prob': txn_prob,
                'context_score': context_score,
                'uncalibrated_prob': uncalibrated_prob
            },
            friction_type=friction_type,
            friction_message=friction_message,
            redacted_input=redacted_input
        )
        
        return response


# Global engine instance (singleton)
_engine_instance = None


def get_detection_engine() -> DetectionEngine:
    """Get or create global detection engine instance"""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = DetectionEngine()
    return _engine_instance
