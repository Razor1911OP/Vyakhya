"""
Vyakhya Detection Engine Test Script
Quick test to validate the engine works end-to-end
"""
import sys
import os
# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.app.schemas import ScoreRequest, TransactionFeatures, ContextSignals
from backend.app.engine import get_detection_engine


def test_normal_payment():
    """Test a normal, low-risk payment"""
    print("\n" + "="*60)
    print("TEST 1: Normal grocery payment")
    print("="*60)
    
    request = ScoreRequest(
        message_text="Thanks for shopping with us! Your bill is Rs. 850",
        transaction=TransactionFeatures(
            amount=850.0,
            amount_vs_history_percentile=45.0,
            oldbalance_orig=50000.0,
            newbalance_orig=49150.0,
            oldbalance_dest=10000.0,
            newbalance_dest=10850.0,
            hour=14,
            day=15,
            transaction_type="PAYMENT",
            txn_count_last_hour=0,
            txn_count_last_day=2,
            fan_out_count=1
        ),
        context=ContextSignals(simulated=True),
        user_id="test_user_001"
    )
    
    engine = get_detection_engine()
    response = engine.score(request)
    
    print(f"Risk Score: {response.risk_score} / 100")
    print(f"Tier: {response.tier.value}")
    print(f"Soft Hold: {response.soft_hold}")
    print(f"Latency: {response.latency_ms}ms")
    print(f"\nTop Reasons:")
    for i, reason in enumerate(response.reason_codes[:3], 1):
        print(f"  {i}. {reason.explanation} (confidence: {reason.confidence:.2f})")
    print(f"\nComponent Scores:")
    for component, score in response.component_scores.items():
        print(f"  {component}: {score:.3f}")


def test_scam_coached_victim():
    """Test a coached-victim scam scenario"""
    print("\n" + "="*60)
    print("TEST 2: Coached victim - digital arrest scam")
    print("="*60)
    
    request = ScoreRequest(
        message_text="URGENT: Your Aadhaar card has been suspended due to illegal activity. "
                     "Transfer Rs 50000 to account 1234567890 immediately to avoid arrest. "
                     "Do not disconnect this call.",
        transaction=TransactionFeatures(
            amount=50000.0,
            amount_vs_history_percentile=98.0,  # Much larger than usual
            oldbalance_orig=75000.0,
            newbalance_orig=25000.0,
            oldbalance_dest=5000.0,
            newbalance_dest=55000.0,
            hour=22,  # Late night
            day=15,
            transaction_type="TRANSFER",
            txn_count_last_hour=3,  # Multiple attempts
            txn_count_last_day=5,
            fan_out_count=1
        ),
        context=ContextSignals(
            call_in_progress=True,  # Key red flag
            screen_share_active=True,  # Very suspicious
            new_device=False,
            geo_velocity_anomaly=False,
            new_login_recent=False,
            pasted_vpa=True,  # Likely pasted from scammer's message
            odd_hour=True,  # 10 PM
            new_payee=True,  # First time
            payee_is_mule=False,
            simulated=True
        ),
        user_id="test_user_002"
    )
    
    engine = get_detection_engine()
    response = engine.score(request)
    
    print(f"Risk Score: {response.risk_score} / 100")
    print(f"Tier: {response.tier.value}")
    print(f"Soft Hold: {response.soft_hold} ⚠️")
    print(f"Latency: {response.latency_ms}ms")
    print(f"\nTop Reasons:")
    for i, reason in enumerate(response.reason_codes[:5], 1):
        print(f"  {i}. {reason.explanation} (confidence: {reason.confidence:.2f})")
    print(f"\nComponent Scores:")
    for component, score in response.component_scores.items():
        print(f"  {component}: {score:.3f}")
    print(f"\nFriction Type: {response.friction_type}")
    print(f"Friction Message:\n{response.friction_message}")


def test_refund_scam():
    """Test a fake refund scam"""
    print("\n" + "="*60)
    print("TEST 3: Fake refund / KYC scam")
    print("="*60)
    
    request = ScoreRequest(
        message_text="Dear customer, your KYC has expired. Click link to update: "
                     "https://fake-bank-kyc.com. Failure to update will result in account suspension.",
        transaction=TransactionFeatures(
            amount=1.0,  # Small amount to verify account
            amount_vs_history_percentile=10.0,
            oldbalance_orig=25000.0,
            newbalance_orig=24999.0,
            oldbalance_dest=0.0,
            newbalance_dest=1.0,
            hour=11,
            day=15,
            transaction_type="PAYMENT",
            txn_count_last_hour=1,
            txn_count_last_day=1,
            fan_out_count=1
        ),
        context=ContextSignals(
            call_in_progress=True,  # On call with "support"
            new_payee=True,
            simulated=True
        ),
        user_id="test_user_003"
    )
    
    engine = get_detection_engine()
    response = engine.score(request)
    
    print(f"Risk Score: {response.risk_score} / 100")
    print(f"Tier: {response.tier.value}")
    print(f"Soft Hold: {response.soft_hold}")
    print(f"Latency: {response.latency_ms}ms")
    print(f"\nTop Reasons:")
    for i, reason in enumerate(response.reason_codes[:3], 1):
        print(f"  {i}. {reason.explanation} (confidence: {reason.confidence:.2f})")
    print(f"\nRedacted Input Preview:")
    if response.redacted_input:
        print(f"  Language: {response.redacted_input.language}")
        print(f"  Redactions: {response.redacted_input.redaction_count}")
        print(f"  Preview: {response.redacted_input.redacted_preview}")


def test_latency_budget():
    """Test that latency is within budget"""
    print("\n" + "="*60)
    print("TEST 4: Latency budget validation (< 300ms target)")
    print("="*60)
    
    engine = get_detection_engine()
    
    # Run 10 quick tests
    latencies = []
    for i in range(10):
        request = ScoreRequest(
            message_text=f"Test message number {i}",
            transaction=TransactionFeatures(
                amount=1000.0,
                oldbalance_orig=50000.0,
                newbalance_orig=49000.0,
                oldbalance_dest=10000.0,
                newbalance_dest=11000.0,
                hour=12,
                day=15,
                transaction_type="PAYMENT"
            ),
            context=ContextSignals(simulated=True),
            user_id=f"test_user_{i:03d}"
        )
        response = engine.score(request)
        latencies.append(response.latency_ms)
    
    avg_latency = sum(latencies) / len(latencies)
    max_latency = max(latencies)
    min_latency = min(latencies)
    
    print(f"Runs: {len(latencies)}")
    print(f"Average latency: {avg_latency:.1f}ms")
    print(f"Min latency: {min_latency}ms")
    print(f"Max latency: {max_latency}ms")
    print(f"Budget: 300ms")
    print(f"Status: {'✅ PASS' if max_latency < 300 else '⚠️ FAIL - optimize models'}")


if __name__ == "__main__":
    print(f"\n{'='*60}")
    print("VYAKHYA DETECTION ENGINE TEST SUITE")
    print(f"{'='*60}")
    
    try:
        test_normal_payment()
        test_scam_coached_victim()
        test_refund_scam()
        test_latency_budget()
        
        print(f"\n{'='*60}")
        print("✅ ALL TESTS COMPLETED")
        print(f"{'='*60}\n")
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
