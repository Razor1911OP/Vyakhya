"""Central constants for the risk engine. Paths can be overridden by environment variables."""
import os
from pathlib import Path

SEED = 42
MAX_INPUT_CHARS = 1000          # inputs are truncated to this before any processing
MODEL_VERSION = "risk-0.2.0"   # 0.2: rule_score in blend, 5%/1% bands, synthetic data v2

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
ARTIFACT_DIR = REPO_ROOT / "model_registry" / "risk" / MODEL_VERSION
METRICS_DIR = REPO_ROOT / "metrics"
FEEDBACK_FILE = REPO_ROOT / "data" / "feedback" / "feedback.jsonl"

SMS_SPAM_PATH = Path(os.getenv("VYAKHYA_SMS_SPAM", r"C:\Users\ACER\Desktop\SMSSpamCollection"))
PAYSIM_PATH = Path(os.getenv("VYAKHYA_PAYSIM", r"C:\Users\ACER\Desktop\PS_20174392719_1491204439457_log.csv"))
MESSAGES_PATH = REPO_ROOT / "data" / "messages.csv"
TRANSACTIONS_PATH = REPO_ROOT / "data" / "transactions.csv"
HANDWRITTEN_PATH = REPO_ROOT / "data" / "handwritten_test.csv"   # test only, frozen
VALIDATION_PATH = REPO_ROOT / "data" / "validation_benign.csv"   # cutoff selection only, frozen
VALIDATION_LABEL = "agent-drafted, same-author caveat"

# Optional text-model comparisons (not shipped). Each runs only if its library imports and the
# model downloads; otherwise it is reported as skipped. Disable with VYAKHYA_COMPARE=0.
COMPARE_MODELS = ["sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"]
COMPARE_ENABLED = False   # decision 2026-10-25: MiniLM skipped, "not evaluated"; TF-IDF + LR stays the baseline
CUTOFF_LABEL = "tuned on synthetic data, re-calibrate at pilot"
USE_VALIDATION_CUTOFFS = False   # decision 2026-10-25: validation_benign.csv not used; synthetic-fold cutoffs kept

HARD_RULE_FLOOR = 90
PAYSIM_LABEL = "public synthetic mobile-money data (PaySim), not UPI"
DATA_DISCLAIMER = ("All metrics come from synthetic and public datasets (UCI SMS Spam, Vyakhya synthetic "
                   "messages, PaySim). They are not production accuracy.")
PIN_DISCLAIMER = "You never enter your UPI PIN to receive money. A PIN is only for sending."
FEEDBACK_QUESTION = "Did someone ask you to share this?"
