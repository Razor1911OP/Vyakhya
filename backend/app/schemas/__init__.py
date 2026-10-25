"""
Vyakhya Schemas
Pydantic models for request/response validation and internal data structures
"""
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional, List, Dict, Literal
from datetime import datetime
from enum import Enum


class TierEnum(str, Enum):
    """Risk tier levels"""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ReasonCode(BaseModel):
    """Plain-language reason code (explainability requirement)"""
    code: str = Field(..., description="Machine-readable reason code")
    explanation: str = Field(..., description="Human-readable explanation")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in this reason")


class RedactedText(BaseModel):
    """Redacted text with metadata (never stores raw text)"""
    text_hash: str = Field(..., description="SHA256 hash for deduplication only")
    redacted_preview: str = Field(..., max_length=100, description="Redacted preview for UI")
    redaction_count: int = Field(..., description="Number of redactions applied")
    language: Optional[str] = Field(None, description="Detected language (en/hi/hi-en)")


class ContextSignals(BaseModel):
    """Context signals from session/device/history"""
    call_in_progress: bool = False
    screen_share_active: bool = False
    new_device: bool = False
    geo_velocity_anomaly: bool = False  # Impossible travel speed
    new_login_recent: bool = False
    pasted_vpa: bool = False  # VPA was pasted, not typed
    odd_hour: bool = False  # < 6 AM or > 10 PM
    new_payee: bool = False
    payee_is_mule: bool = False  # From graph analysis (ROADMAP in MVP)
    
    # Mark simulated signals
    simulated: bool = True  # MVP: all context is simulated


class TransactionFeatures(BaseModel):
    """Transaction-level features for XGBoost model"""
    amount: float = Field(..., gt=0, description="Transaction amount in INR")
    amount_vs_history_percentile: Optional[float] = Field(None, ge=0, le=100)
    oldbalance_orig: float = Field(..., ge=0)
    newbalance_orig: float = Field(..., ge=0)
    oldbalance_dest: float = Field(..., ge=0)
    newbalance_dest: float = Field(..., ge=0)
    
    # Computed features
    error_balance_orig: Optional[float] = None  # newbalance_orig + amount - oldbalance_orig
    error_balance_dest: Optional[float] = None  # oldbalance_dest + amount - newbalance_dest
    
    hour: int = Field(..., ge=0, lt=24)
    day: int = Field(..., ge=1, le=31)
    transaction_type: Literal["PAYMENT", "TRANSFER", "DEBIT"] = "PAYMENT"
    
    # Velocity features
    txn_count_last_hour: int = Field(0, ge=0)
    txn_count_last_day: int = Field(0, ge=0)
    fan_out_count: int = Field(0, ge=0, description="Unique payees in last 24h")

    # Added 2026-10-25 for the risk engine (optional, backward compatible)
    direction: Optional[Literal["debit", "collect", "credit"]] = Field(
        None, description="Money flow of the pending transaction; 'collect' = pull request the user approves")
    beneficiary_prior_txns: Optional[int] = Field(
        None, ge=0, description="Payments the payee has received before; missing = unknown, treated as a new payee")


class ScoreRequest(BaseModel):
    """Request payload for /score endpoint"""
    
    # Message (optional, for text analysis)
    message_text: Optional[str] = Field(None, max_length=1000, description="Message prompting payment")
    
    # Transaction details
    transaction: TransactionFeatures
    
    # Context signals (simulated in MVP)
    context: ContextSignals = Field(default_factory=ContextSignals)
    
    # User identifier (for rate limiting, not stored with raw text)
    user_id: str = Field(..., description="Anonymous user identifier")
    
    @field_validator('message_text')
    @classmethod
    def validate_message(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not v:
                return None
        return v


class ModelVersion(BaseModel):
    """Model version metadata for audit trail"""
    model_config = ConfigDict(protected_namespaces=())
    model_name: str
    version: str
    used: bool  # Whether this model was actually used (or fell back)


class ScoreResponse(BaseModel):
    """Response from /score endpoint"""
    model_config = ConfigDict(protected_namespaces=())
    
    # Core risk assessment
    risk_score: int = Field(..., ge=0, le=100, description="Calibrated risk score R")
    tier: TierEnum
    soft_hold: bool = Field(..., description="Whether payment should be held before debit")
    
    # Explainability (core product identity)
    reason_codes: List[ReasonCode] = Field(..., min_length=1, description="Plain-language reasons")
    
    # Model transparency
    model_versions: List[ModelVersion] = Field(..., description="Models used in this decision")
    
    # Performance
    latency_ms: int = Field(..., description="Total scoring time")
    
    # Component scores (for analysis dashboard)
    component_scores: Dict[str, float] = Field(
        default_factory=dict,
        description="Scores from individual components (text, txn, context, fusion)"
    )
    
    # UI guidance
    friction_type: Optional[str] = Field(None, description="UI friction pattern to show")
    friction_message: Optional[str] = Field(None, description="Message to display to user")
    
    # Request echo (for logging, with redacted text)
    redacted_input: Optional[RedactedText] = None


class AuditLogEntry(BaseModel):
    """Immutable audit log entry (no raw text, ever)"""
    model_config = ConfigDict(protected_namespaces=())
    timestamp: datetime
    user_id: str
    risk_score: int
    tier: TierEnum
    soft_hold: bool
    reason_codes: List[str]  # Just the codes, not full objects
    model_versions: Dict[str, str]  # model_name -> version
    latency_ms: int
    decision: Optional[Literal["allow", "hold", "released", "blocked"]] = None
    analyst_id: Optional[str] = None
    analyst_note: Optional[str] = None
