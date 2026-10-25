"""
Vyakhya Configuration
Central config management with environment variable overrides
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal


class Settings(BaseSettings):
    """Application settings with secure defaults"""
    
    # App Identity
    app_name: str = "Vyakhya"
    app_version: str = "0.1.0"
    environment: Literal["development", "production"] = "development"
    
    # API Settings
    api_prefix: str = "/api/v1"
    score_latency_budget_ms: int = 300  # Hard requirement: < 300ms
    
    # Security
    secret_key: str = "CHANGE_ME_IN_PRODUCTION_USE_openssl_rand_hex_32"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60
    
    # MongoDB
    mongodb_url: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "vyakhya"
    
    # Model Registry
    model_registry_path: str = "./model_registry"
    
    # Detection Engine Config
    text_model_timeout_ms: int = 200  # Fallback to TF-IDF if HF exceeds this
    text_model_primary: str = "distilbert-base-multilingual-cased"  # HF model ID
    text_model_fallback: str = "tfidf_lr"  # Local trained model
    
    # Tier Cutoffs (calibrated risk score R in [0, 100])
    tier_low_max: int = 39
    tier_medium_max: int = 69
    tier_high_max: int = 84
    # CRITICAL >= 85
    
    # Privacy & Retention
    raw_text_retention_days: int = 0  # Never store raw text
    features_retention_days: int = 90
    case_retention_days: int = 365
    
    # Rate Limiting (per user)
    rate_limit_requests_per_minute: int = 100
    alert_fatigue_target_per_week: int = 1  # Alert budget target
    
    # Soft-Hold Policy
    soft_hold_enabled: bool = True  # Kill-switch
    soft_hold_auto_expiry_minutes: int = 30
    dual_review_threshold: int = 85  # CRITICAL tier requires dual review
    
    # Feature Flags
    enable_hf_model: bool = True  # Toggle HF model (falls back to TF-IDF)
    enable_clustering: bool = False  # Novelty detection (offline only in MVP)
    
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        protected_namespaces=("settings_",),
    )


# Global settings instance
settings = Settings()
