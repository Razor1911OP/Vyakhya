"""
Vyakhya Tier Policy Engine
Maps risk score R to tier and determines friction/hold policy
"""
from typing import Tuple, Optional
from backend.app.schemas import TierEnum, ReasonCode
from backend.app.core.config import settings
from backend.app.core.logging import get_logger

logger = get_logger(__name__)


class TierPolicy:
    """
    Tier assignment and friction policy
    
    Tiers:
    - LOW (0-39): Silent allow, log only
    - MEDIUM (40-69): One inline nudge, one-tap proceed
    - HIGH (70-84): Named-reason friction + 30s wait
    - CRITICAL (85-100): Soft-hold before debit, analyst review
    """
    
    def __init__(self):
        self.tier_cutoffs = {
            TierEnum.LOW: (0, settings.tier_low_max),
            TierEnum.MEDIUM: (settings.tier_low_max + 1, settings.tier_medium_max),
            TierEnum.HIGH: (settings.tier_medium_max + 1, settings.tier_high_max),
            TierEnum.CRITICAL: (settings.tier_high_max + 1, 100),
        }
    
    def assign_tier(self, risk_score: int) -> TierEnum:
        """Assign tier based on risk score R"""
        for tier, (low, high) in self.tier_cutoffs.items():
            if low <= risk_score <= high:
                return tier
        
        # Fallback (should never reach here)
        logger.error(f"Risk score {risk_score} out of bounds, defaulting to CRITICAL")
        return TierEnum.CRITICAL
    
    def should_soft_hold(self, tier: TierEnum) -> bool:
        """Determine if payment should be held before debit"""
        if not settings.soft_hold_enabled:
            return False
        
        return tier == TierEnum.CRITICAL
    
    def get_friction_config(
        self,
        tier: TierEnum,
        top_reasons: list[ReasonCode]
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Get UI friction configuration for tier
        
        Args:
            tier: Assigned risk tier
            top_reasons: Top reason codes (for HIGH/CRITICAL messaging)
        
        Returns:
            (friction_type, friction_message)
        """
        
        if tier == TierEnum.LOW:
            return None, None
        
        elif tier == TierEnum.MEDIUM:
            return "inline_nudge", (
                "This payment shows some unusual patterns. "
                "Please verify the recipient before proceeding."
            )
        
        elif tier == TierEnum.HIGH:
            # Named-reason friction with 30s wait
            top_reason = top_reasons[0].explanation if top_reasons else "unusual patterns detected"
            return "named_friction_30s", (
                f"⚠️ Security Check Required\n\n"
                f"We noticed: {top_reason}\n\n"
                f"Are you on a call with someone guiding this payment?\n"
                f"If yes, this may be a scam. Hang up and verify independently.\n\n"
                f"You can proceed after 30 seconds."
            )
        
        elif tier == TierEnum.CRITICAL:
            # Soft-hold messaging
            return "soft_hold", (
                "🛡️ Payment Paused for Your Safety\n\n"
                "We've temporarily held this transfer to protect you from potential fraud.\n\n"
                "Our team will review this shortly. You'll receive a call from your bank "
                "to verify this transaction.\n\n"
                "⚠️ Your bank will NEVER ask for your OTP, PIN, or CVV.\n\n"
                "Expected review time: 15-30 minutes"
            )
        
        return None, None
    
    def get_tier_display_name(self, tier: TierEnum) -> str:
        """Get human-readable tier name"""
        return {
            TierEnum.LOW: "Low Risk",
            TierEnum.MEDIUM: "Medium Risk",
            TierEnum.HIGH: "High Risk",
            TierEnum.CRITICAL: "Critical - Under Review"
        }[tier]


# Global instance
_tier_policy_instance = None


def get_tier_policy() -> TierPolicy:
    """Get or create global tier policy engine"""
    global _tier_policy_instance
    if _tier_policy_instance is None:
        _tier_policy_instance = TierPolicy()
    return _tier_policy_instance
