"""
Vyakhya Text Model
Primary: HF multilingual model with timeout
Fallback: TF-IDF + Logistic Regression (always loaded, fast)
"""
import time
import pickle
import numpy as np
from typing import Tuple, Optional
from pathlib import Path

from backend.app.core.config import settings
from backend.app.core.logging import get_logger

logger = get_logger(__name__)


class TextModel:
    """
    Text classification with primary/fallback strategy
    """
    
    def __init__(self, registry_path: str = "./model_registry"):
        self.registry_path = Path(registry_path)
        self.primary_model = None
        self.primary_loaded = False
        self.fallback_model = None
        self.fallback_vectorizer = None
        self.fallback_loaded = False
        
        # Load fallback (always succeeds or raises)
        self._load_fallback()
        
        # Try to load primary if enabled
        if settings.enable_hf_model:
            self._load_primary()
    
    def _load_fallback(self) -> None:
        """Load TF-IDF + LR fallback model (must succeed)"""
        try:
            fallback_path = self.registry_path / "tfidf_lr" / "v1"
            
            # Check if model exists
            if not fallback_path.exists():
                logger.warning(f"Fallback model not found at {fallback_path}, creating dummy")
                self._create_dummy_fallback()
                return
            
            with open(fallback_path / "vectorizer.pkl", "rb") as f:
                self.fallback_vectorizer = pickle.load(f)
            
            with open(fallback_path / "model.pkl", "rb") as f:
                self.fallback_model = pickle.load(f)
            
            self.fallback_loaded = True
            logger.info("Fallback text model loaded successfully", extra={
                'model': 'tfidf_lr',
                'version': 'v1'
            })
        
        except Exception as e:
            logger.error(f"Failed to load fallback model: {e}")
            # Create emergency dummy fallback
            self._create_dummy_fallback()
    
    def _create_dummy_fallback(self) -> None:
        """Create a dummy fallback for development (returns mid-range probabilities)"""
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        
        logger.warning("Creating dummy fallback model - TRAIN REAL MODEL BEFORE PRODUCTION")
        
        # Dummy training data
        dummy_texts = [
            "congratulations you won lottery",
            "urgent verify your kyc now",
            "your account will expire today",
            "hello how are you",
            "thanks for the payment",
            "see you tomorrow"
        ]
        dummy_labels = [1, 1, 1, 0, 0, 0]
        
        self.fallback_vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),
            max_features=1000,
            min_df=1
        )
        X = self.fallback_vectorizer.fit_transform(dummy_texts)
        
        self.fallback_model = LogisticRegression(random_state=42)
        self.fallback_model.fit(X, dummy_labels)
        
        self.fallback_loaded = True
        logger.warning("Dummy fallback model created - THIS IS NOT PRODUCTION READY")
    
    def _load_primary(self) -> None:
        """Try to load HF model (may fail, non-fatal)"""
        try:
            from transformers import pipeline
            
            model_path = self.registry_path / settings.text_model_primary / "v1"
            
            if model_path.exists():
                # Load fine-tuned local model
                self.primary_model = pipeline(
                    "text-classification",
                    model=str(model_path),
                    device=-1  # CPU only (GPU would be device=0)
                )
                logger.info(f"Primary text model loaded from {model_path}")
            else:
                # Try HF hub
                logger.info(f"Loading primary model from HF hub: {settings.text_model_primary}")
                self.primary_model = pipeline(
                    "text-classification",
                    model=settings.text_model_primary,
                    device=-1
                )
            
            self.primary_loaded = True
            logger.info("Primary text model loaded successfully", extra={
                'model': settings.text_model_primary
            })
        
        except Exception as e:
            logger.warning(f"Failed to load primary model: {e}, will use fallback only")
            self.primary_loaded = False
    
    def predict(self, text: str, timeout_ms: Optional[int] = None) -> Tuple[float, str, int]:
        """
        Predict scam probability for text
        
        Args:
            text: Redacted message text
            timeout_ms: Max time allowed (uses config default if None)
        
        Returns:
            (probability, model_used, latency_ms)
        """
        if timeout_ms is None:
            timeout_ms = settings.text_model_timeout_ms
        
        # Try primary first (if loaded and enabled)
        if self.primary_loaded and settings.enable_hf_model:
            start_time = time.perf_counter()
            try:
                result = self.primary_model(text[:512], truncation=True)  # HF models have token limits
                latency_ms = int((time.perf_counter() - start_time) * 1000)
                
                # Check if within budget
                if latency_ms > timeout_ms:
                    logger.warning(f"Primary model exceeded timeout ({latency_ms}ms > {timeout_ms}ms), falling back")
                    return self._predict_fallback(text)
                
                # Extract probability (HF returns label + score)
                # Assuming binary classification with labels LABEL_0 (legit) and LABEL_1 (scam)
                prob = result[0]['score'] if result[0]['label'] == 'LABEL_1' else (1 - result[0]['score'])
                
                return prob, settings.text_model_primary, latency_ms
            
            except Exception as e:
                logger.warning(f"Primary model prediction failed: {e}, falling back")
                return self._predict_fallback(text)
        
        # Use fallback
        return self._predict_fallback(text)
    
    def _predict_fallback(self, text: str) -> Tuple[float, str, int]:
        """Fallback prediction with TF-IDF + LR"""
        start_time = time.perf_counter()
        
        try:
            X = self.fallback_vectorizer.transform([text])
            prob = self.fallback_model.predict_proba(X)[0][1]  # Probability of class 1 (scam)
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            
            return prob, "tfidf_lr", latency_ms
        
        except Exception as e:
            logger.error(f"Fallback model failed: {e}, returning neutral score")
            return 0.5, "tfidf_lr_error", 0


# Global instance (loaded once at startup)
_text_model_instance = None


def get_text_model() -> TextModel:
    """Get or create global text model instance"""
    global _text_model_instance
    if _text_model_instance is None:
        _text_model_instance = TextModel(registry_path=settings.model_registry_path)
    return _text_model_instance
