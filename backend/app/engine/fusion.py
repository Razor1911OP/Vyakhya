"""
Vyakhya Fusion Layer
Combines text, transaction, and context scores into calibrated risk score R ∈ [0, 100]
"""
import pickle
import numpy as np
from typing import Tuple, Dict
from pathlib import Path

from backend.app.core.config import settings
from backend.app.core.logging import get_logger

logger = get_logger(__name__)


class FusionModel:
    """
    Fuses component scores into final risk score
    Uses simple weighted ensemble (MVP) or trained gradient boosting (production)
    """
    
    def __init__(self, registry_path: str = "./model_registry"):
        self.registry_path = Path(registry_path)
        self.fusion_model = None
        self.calibrator = None
        self.model_loaded = False
        
        # Default weights (used if trained model not available)
        self.default_weights = {
            'text_prob': 0.40,  # Text is strong signal for scam type
            'txn_prob': 0.35,  # Transaction features catch balance/velocity issues
            'context_score': 0.25,  # Context signals catch social engineering
        }
        
        self._load_model()
    
    def _load_model(self) -> None:
        """Load fusion model and calibrator from registry"""
        try:
            fusion_path = self.registry_path / "fusion" / "v1"
            
            if not fusion_path.exists():
                logger.warning(f"Fusion model not found at {fusion_path}, using default weights")
                return
            
            with open(fusion_path / "fusion_model.pkl", "rb") as f:
                self.fusion_model = pickle.load(f)
            
            with open(fusion_path / "calibrator.pkl", "rb") as f:
                self.calibrator = pickle.load(f)
            
            self.model_loaded = True
            logger.info("Fusion model loaded successfully", extra={
                'model': 'fusion',
                'version': 'v1'
            })
        
        except Exception as e:
            logger.warning(f"Failed to load fusion model: {e}, using default weights")
            self.model_loaded = False
    
    def fuse(
        self,
        text_prob: float,
        txn_prob: float,
        context_score: float
    ) -> Tuple[float, float]:
        """
        Fuse component scores into final risk probability and calibrated R score
        
        Args:
            text_prob: Text model probability [0, 1]
            txn_prob: Transaction model probability [0, 1]
            context_score: Context rules score [0, 1]
        
        Returns:
            (uncalibrated_prob, calibrated_R)
            uncalibrated_prob: fused probability [0, 1]
            calibrated_R: calibrated risk score [0, 100]
        """
        
        # If trained fusion model exists, use it
        if self.model_loaded and self.fusion_model is not None:
            features = np.array([[text_prob, txn_prob, context_score]])
            uncalibrated_prob = float(self.fusion_model.predict_proba(features)[0][1])
        else:
            # Weighted average (simple fusion)
            uncalibrated_prob = (
                self.default_weights['text_prob'] * text_prob +
                self.default_weights['txn_prob'] * txn_prob +
                self.default_weights['context_score'] * context_score
            )
        
        # Calibrate to R ∈ [0, 100]
        if self.model_loaded and self.calibrator is not None:
            calibrated_prob = float(self.calibrator.transform(np.array([[uncalibrated_prob]]))[0])
        else:
            # Simple linear calibration (production needs isotonic/Platt)
            calibrated_prob = uncalibrated_prob
        
        # Scale to [0, 100]
        R = int(round(calibrated_prob * 100))
        R = max(0, min(100, R))  # Clamp
        
        logger.debug(f"Fusion computed: R={R}", extra={
            'text_prob': text_prob,
            'txn_prob': txn_prob,
            'context_score': context_score,
            'uncalibrated': uncalibrated_prob,
            'R': R
        })
        
        return uncalibrated_prob, float(R)


# Global instance
_fusion_model_instance = None


def get_fusion_model() -> FusionModel:
    """Get or create global fusion model instance"""
    global _fusion_model_instance
    if _fusion_model_instance is None:
        _fusion_model_instance = FusionModel(registry_path=settings.model_registry_path)
    return _fusion_model_instance
