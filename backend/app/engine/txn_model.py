"""
Vyakhya Transaction Model
XGBoost on transaction features with computed balance checks
"""
import pickle
import time
import numpy as np
from typing import Tuple
from pathlib import Path

from backend.app.schemas import TransactionFeatures
from backend.app.core.config import settings
from backend.app.core.logging import get_logger

logger = get_logger(__name__)


class TransactionModel:
    """XGBoost model for transaction fraud detection"""
    
    def __init__(self, registry_path: str = "./model_registry"):
        self.registry_path = Path(registry_path)
        self.model = None
        self.model_loaded = False
        self.feature_names = []
        
        self._load_model()
    
    def _load_model(self) -> None:
        """Load XGBoost model from registry"""
        try:
            model_path = self.registry_path / "xgboost_txn" / "v1"
            
            if not model_path.exists():
                logger.warning(f"Transaction model not found at {model_path}, creating dummy")
                self._create_dummy_model()
                return
            
            with open(model_path / "model.pkl", "rb") as f:
                self.model = pickle.load(f)
            
            with open(model_path / "feature_names.pkl", "rb") as f:
                self.feature_names = pickle.load(f)
            
            self.model_loaded = True
            logger.info("Transaction model loaded successfully", extra={
                'model': 'xgboost_txn',
                'version': 'v1',
                'n_features': len(self.feature_names)
            })
        
        except Exception as e:
            logger.error(f"Failed to load transaction model: {e}")
            self._create_dummy_model()
    
    def _create_dummy_model(self) -> None:
        """Create dummy XGBoost model for development"""
        import xgboost as xgb
        
        logger.warning("Creating dummy transaction model - TRAIN REAL MODEL BEFORE PRODUCTION")
        
        # Dummy training data (10 samples with key features)
        self.feature_names = [
            'amount', 'amount_vs_history_percentile', 'error_balance_orig',
            'error_balance_dest', 'hour', 'day', 'txn_count_last_hour',
            'txn_count_last_day', 'fan_out_count', 'type_PAYMENT',
            'type_TRANSFER', 'type_DEBIT'
        ]
        
        # Create dummy data
        X_dummy = np.random.rand(10, len(self.feature_names))
        y_dummy = np.array([0, 0, 0, 0, 0, 1, 1, 1, 1, 1])  # Half fraud, half legit
        
        dtrain = xgb.DMatrix(X_dummy, label=y_dummy, feature_names=self.feature_names)
        
        params = {
            'objective': 'binary:logistic',
            'max_depth': 3,
            'eta': 0.1,
            'eval_metric': 'auc'
        }
        
        self.model = xgb.train(params, dtrain, num_boost_round=10)
        self.model_loaded = True
        logger.warning("Dummy transaction model created - THIS IS NOT PRODUCTION READY")
    
    def _compute_features(self, txn: TransactionFeatures) -> np.ndarray:
        """Compute features from transaction, including balance checks"""
        
        # Compute balance error features (UPI fraud detection pattern)
        error_balance_orig = txn.newbalance_orig + txn.amount - txn.oldbalance_orig
        error_balance_dest = txn.oldbalance_dest + txn.amount - txn.newbalance_dest
        
        # One-hot encode transaction type
        type_payment = 1 if txn.transaction_type == "PAYMENT" else 0
        type_transfer = 1 if txn.transaction_type == "TRANSFER" else 0
        type_debit = 1 if txn.transaction_type == "DEBIT" else 0
        
        # Assemble feature vector
        features = {
            'amount': txn.amount,
            'amount_vs_history_percentile': txn.amount_vs_history_percentile or 50.0,
            'error_balance_orig': error_balance_orig,
            'error_balance_dest': error_balance_dest,
            'hour': txn.hour,
            'day': txn.day,
            'txn_count_last_hour': txn.txn_count_last_hour,
            'txn_count_last_day': txn.txn_count_last_day,
            'fan_out_count': txn.fan_out_count,
            'type_PAYMENT': type_payment,
            'type_TRANSFER': type_transfer,
            'type_DEBIT': type_debit
        }
        
        # Align with model's expected feature order
        feature_vector = np.array([features[name] for name in self.feature_names])
        return feature_vector
    
    def predict(self, txn: TransactionFeatures) -> Tuple[float, int]:
        """
        Predict fraud probability for transaction
        
        Args:
            txn: Transaction features
        
        Returns:
            (probability, latency_ms)
        """
        start_time = time.perf_counter()
        
        try:
            import xgboost as xgb
            
            # Compute features
            feature_vector = self._compute_features(txn)
            
            # Create DMatrix
            dtest = xgb.DMatrix(
                feature_vector.reshape(1, -1),
                feature_names=self.feature_names
            )
            
            # Predict
            prob = float(self.model.predict(dtest)[0])
            
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            
            return prob, latency_ms
        
        except Exception as e:
            logger.error(f"Transaction model prediction failed: {e}, returning neutral score")
            return 0.5, 0


# Global instance
_txn_model_instance = None


def get_txn_model() -> TransactionModel:
    """Get or create global transaction model instance"""
    global _txn_model_instance
    if _txn_model_instance is None:
        _txn_model_instance = TransactionModel(registry_path=settings.model_registry_path)
    return _txn_model_instance
