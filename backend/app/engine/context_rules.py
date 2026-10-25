"""
Vyakhya Context Rules Engine
Session, velocity, and behavioral signal analysis
"""
from typing import Tuple, List
from backend.app.schemas import ContextSignals, TransactionFeatures, ReasonCode
from backend.app.core.logging import get_logger

logger = get_logger(__name__)


class ContextRulesEngine:
    """
    Evaluates context signals and generates risk contributions
    
    Philosophy: A missing signal WIDENS the review band, never silently lowers risk
    """
    
    # Risk weights for each signal (0-1 scale, will be combined in fusion)
    SIGNAL_WEIGHTS = {
        'call_in_progress': 0.25,  # Strong indicator of social engineering
        'screen_share_active': 0.30,  # Very strong indicator
        'new_device': 0.10,  # Moderate risk
        'geo_velocity_anomaly': 0.15,  # Impossible travel
        'new_login_recent': 0.08,
        'pasted_vpa': 0.12,  # Victim often pastes VPA from scammer's message
        'odd_hour': 0.08,  # < 6 AM or > 10 PM
        'new_payee': 0.15,  # Combined with other signals
        'payee_is_mule': 0.35,  # Very high risk (ROADMAP)
    }
    
    # Reason code templates
    REASON_TEMPLATES = {
        'call_in_progress': "Payment initiated during an active phone call",
        'screen_share_active': "Screen sharing detected during payment",
        'new_device': "Payment from a new or unrecognized device",
        'geo_velocity_anomaly': "Impossible location change detected",
        'new_login_recent': "Recent login from new location",
        'pasted_vpa': "Payment address appears to be pasted, not typed",
        'odd_hour': "Transaction at unusual hour (late night or early morning)",
        'new_payee': "First time paying this recipient",
        'payee_is_mule': "Recipient flagged as potential money mule account",
        'high_velocity': "Unusually high transaction frequency",
        'high_fan_out': "Payments to many different recipients in short time",
        'large_amount_anomaly': "Transaction amount is much larger than your typical payments",
    }
    
    def compute_context_score(
        self,
        context: ContextSignals,
        txn: TransactionFeatures
    ) -> Tuple[float, List[ReasonCode]]:
        """
        Compute risk contribution from context signals
        
        Args:
            context: Context signals from session/device
            txn: Transaction features (for velocity/amount checks)
        
        Returns:
            (context_risk_score, reason_codes)
        """
        total_risk = 0.0
        reasons = []
        
        # Evaluate boolean signals
        for signal_name, weight in self.SIGNAL_WEIGHTS.items():
            if getattr(context, signal_name, False):
                total_risk += weight
                reasons.append(ReasonCode(
                    code=signal_name,
                    explanation=self.REASON_TEMPLATES[signal_name],
                    confidence=weight
                ))
        
        # Velocity checks
        velocity_risk, velocity_reasons = self._check_velocity(txn)
        total_risk += velocity_risk
        reasons.extend(velocity_reasons)
        
        # Amount anomaly check
        if txn.amount_vs_history_percentile and txn.amount_vs_history_percentile > 95:
            anomaly_weight = 0.20
            total_risk += anomaly_weight
            reasons.append(ReasonCode(
                code='large_amount_anomaly',
                explanation=self.REASON_TEMPLATES['large_amount_anomaly'],
                confidence=anomaly_weight
            ))
        
        # Normalize to [0, 1] (cap at 1.0)
        context_score = min(total_risk, 1.0)
        
        # Sort reasons by confidence (highest first)
        reasons.sort(key=lambda r: r.confidence, reverse=True)
        
        logger.debug(f"Context score computed: {context_score:.3f}", extra={
            'context_score': context_score,
            'reason_count': len(reasons),
            'simulated': context.simulated
        })
        
        return context_score, reasons
    
    def _check_velocity(self, txn: TransactionFeatures) -> Tuple[float, List[ReasonCode]]:
        """Check transaction velocity patterns"""
        risk = 0.0
        reasons = []
        
        # High velocity (>5 txn/hour or >20 txn/day)
        if txn.txn_count_last_hour > 5:
            velocity_weight = min(0.15, 0.05 + 0.02 * (txn.txn_count_last_hour - 5))
            risk += velocity_weight
            reasons.append(ReasonCode(
                code='high_velocity',
                explanation=self.REASON_TEMPLATES['high_velocity'],
                confidence=velocity_weight
            ))
        
        # High fan-out (money mule pattern)
        if txn.fan_out_count > 5:
            fanout_weight = min(0.20, 0.10 + 0.02 * (txn.fan_out_count - 5))
            risk += fanout_weight
            reasons.append(ReasonCode(
                code='high_fan_out',
                explanation=self.REASON_TEMPLATES['high_fan_out'],
                confidence=fanout_weight
            ))
        
        return risk, reasons


# Global instance
_context_engine_instance = None


def get_context_engine() -> ContextRulesEngine:
    """Get or create global context rules engine"""
    global _context_engine_instance
    if _context_engine_instance is None:
        _context_engine_instance = ContextRulesEngine()
    return _context_engine_instance
