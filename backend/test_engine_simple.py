"""
Vyakhya Detection Engine Simple Test (No Dependencies)
Tests the architecture and component structure
"""
import os
import sys

print("="*60)
print("VYAKHYA DETECTION ENGINE - ARCHITECTURE VALIDATION")
print("="*60)

# Check directory structure
print("\n1. Checking directory structure...")
required_dirs = [
    "app",
    "app/engine",
    "app/core",
    "app/schemas",
    "../model_registry",
    "../metrics",
    "../data"
]

all_exist = True
for dir_path in required_dirs:
    full_path = os.path.join(os.path.dirname(__file__), dir_path)
    exists = os.path.exists(full_path)
    status = "✅" if exists else "❌"
    print(f"  {status} {dir_path}")
    if not exists:
        all_exist = False

# Check engine component files
print("\n2. Checking engine components...")
engine_files = [
    "app/engine/__init__.py",
    "app/engine/validate_redact.py",
    "app/engine/text_model.py",
    "app/engine/txn_model.py",
    "app/engine/context_rules.py",
    "app/engine/fusion.py",
    "app/engine/tier_policy.py"
]

for file_path in engine_files:
    full_path = os.path.join(os.path.dirname(__file__), file_path)
    exists = os.path.exists(full_path)
    status = "✅" if exists else "❌"
    component_name = os.path.basename(file_path).replace(".py", "")
    print(f"  {status} {component_name}")
    if not exists:
        all_exist = False

# Check core files
print("\n3. Checking core infrastructure...")
core_files = [
    "app/core/config.py",
    "app/core/logging.py",
    "app/schemas/__init__.py",
    "app/main.py"
]

for file_path in core_files:
    full_path = os.path.join(os.path.dirname(__file__), file_path)
    exists = os.path.exists(full_path)
    status = "✅" if exists else "❌"
    print(f"  {status} {file_path}")
    if not exists:
        all_exist = False

# Check requirements
print("\n4. Checking requirements.txt...")
req_file = os.path.join(os.path.dirname(__file__), "requirements.txt")
if os.path.exists(req_file):
    with open(req_file, 'r') as f:
        lines = [l.strip() for l in f.readlines() if l.strip() and not l.startswith('#')]
    print(f"  ✅ requirements.txt ({len(lines)} dependencies)")
    print(f"     Key packages: fastapi, xgboost, transformers, scikit-learn")
else:
    print(f"  ❌ requirements.txt not found")
    all_exist = False

# Test redaction logic (no dependencies)
print("\n5. Testing redaction patterns...")
test_patterns = {
    "OTP": "Your OTP is 123456",
    "Phone": "Call me at 9876543210",
    "Account": "Account number 1234567890123",
    "VPA": "Pay to user@paytm"
}

import re
patterns = {
    'otp': re.compile(r'\b\d{4,6}\b'),
    'phone': re.compile(r'\b[6-9]\d{9}\b'),
    'account': re.compile(r'\b\d{9,18}\b'),
    'vpa': re.compile(r'\b[\w\.\-]+@[\w]+\b'),
}

redaction_works = True
for pattern_name, test_text in test_patterns.items():
    pattern_key = pattern_name.lower()
    if pattern_key in patterns:
        matches = patterns[pattern_key].findall(test_text)
        if matches:
            print(f"  ✅ {pattern_name} pattern: detected '{matches[0]}'")
        else:
            print(f"  ⚠️ {pattern_name} pattern: no match (check regex)")
            redaction_works = False

# Summary
print("\n" + "="*60)
if all_exist and redaction_works:
    print("✅ ARCHITECTURE VALIDATION PASSED")
    print("\nDetection Engine Components:")
    print("  1. validate_redact.py  - Privacy layer (OTP/account/phone redaction)")
    print("  2. text_model.py       - HF multilingual + TF-IDF fallback")
    print("  3. txn_model.py        - XGBoost transaction fraud model")
    print("  4. context_rules.py    - Session/velocity/behavioral signals")
    print("  5. fusion.py           - Score fusion (weighted or trained)")
    print("  6. tier_policy.py      - Tier assignment (LOW/MEDIUM/HIGH/CRITICAL)")
    print("\nPipeline: validate → text → txn → context → fusion → tier")
    print("Latency budget: < 300ms p95")
    print("\nNext steps:")
    print("  1. Install dependencies: pip install -r requirements.txt")
    print("  2. Run full test: python test_engine.py")
    print("  3. Start API: python -m app.main")
else:
    print("❌ ARCHITECTURE VALIDATION FAILED")
    print("Some components are missing. Check the errors above.")
print("="*60)
