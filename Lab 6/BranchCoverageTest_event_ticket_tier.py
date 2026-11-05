"""Lab 6: Chhavi S | PES1UG24CS132. Expected values derived from source prices."""
import pytest
from event_ticket_tier import process_ticket_manifest, monitor_gate_flow


def m(tier="general", orders=None, confirmed=True, lounge=False):
    return {"is_confirmed": confirmed, "tier": tier,
            "exclusive_lounge": lounge, "orders": orders or []}


def run(manifests, tax=0.0):
    return process_ticket_manifest(manifests, tax)


# ---- input validation (both operands of the `or`) ----
def test_single_general_order():
    assert run([m(orders=[{"qty": 2, "promo": ""}])], 0.1) == {"total_revenue": 99.0, "status": "COMPLETED"}

def test_non_list_raises():
    with pytest.raises(ValueError, match="Invalid manifests list or tax rate") as error:
        run("bad")
    assert str(error.value) == "Invalid manifests list or tax rate"

def test_negative_tax_raises():
    with pytest.raises(ValueError, match="Invalid manifests list or tax rate") as error:
        run([], -0.1)
    assert str(error.value) == "Invalid manifests list or tax rate"

def test_empty_list_zero_tax_ok():
    assert run([]) == {"total_revenue": 0.0, "status": "ZERO_SALES"}


# ---- manifest-level branches ----
def test_unconfirmed_skipped():
    assert run([m(confirmed=False, orders=[{"qty": 1}])])["status"] == "ZERO_SALES"

def test_missing_keys_use_defaults():
    # no is_confirmed -> skipped
    assert run([{"tier": "vip"}])["status"] == "ZERO_SALES"
    # confirmed but no tier/orders -> general with no orders
    assert run([{"is_confirmed": True}])["status"] == "ZERO_SALES"

def test_vip_price():
    assert run([m("vip", [{"qty": 1}])])["total_revenue"] == 150.0

def test_premium_price():
    assert run([m("premium", [{"qty": 1}])])["total_revenue"] == 90.0

def test_general_price():
    assert run([m("general", [{"qty": 1}])])["total_revenue"] == 45.0

def test_unknown_tier_rejected_and_skipped():
    assert run([m("platinum", [{"qty": 1}])])["status"] == "ZERO_SALES"

def test_lounge_true_and_false():
    assert run([m(orders=[{"qty": 1}], lounge=True)])["total_revenue"] == 120.0
    assert run([m(orders=[{"qty": 1}], lounge=False)])["total_revenue"] == 45.0


# ---- order-level branches ----
def test_qty_zero_and_negative_rejected():
    assert run([m(orders=[{"qty": 0}])])["status"] == "ZERO_SALES"
    assert run([m(orders=[{"qty": -3}])])["status"] == "ZERO_SALES"
    assert run([m(orders=[{}])])["status"] == "ZERO_SALES"

def test_fraud_non_vip_continues():
    r = run([m("general", [{"qty": 1, "promo": "FRAUD_RISK"}, {"qty": 1}])])
    assert r["total_revenue"] == 90.0

def test_fraud_vip_breaks_and_zeros_manifest():
    r = run([m("vip", [{"qty": 2}, {"qty": 1, "promo": "FRAUD_RISK"}, {"qty": 1}])])
    assert r["status"] == "ZERO_SALES"

def test_earlybird_discount():
    assert run([m(orders=[{"qty": 10, "promo": "EARLYBIRD"}])])["total_revenue"] == 360.0

def test_bulk_discount_qty_5_and_4():
    assert run([m(orders=[{"qty": 5}])])["total_revenue"] == 205.0
    assert run([m(orders=[{"qty": 4}])])["total_revenue"] == 180.0

def test_unknown_promo_treated_as_normal():
    assert run([m(orders=[{"qty": 1, "promo": "WHATEVER"}])])["total_revenue"] == 45.0


# ---- final status branches ----
def test_tax_applied_rounding():
    assert run([m(orders=[{"qty": 1}])], 0.075)["total_revenue"] == 48.38

def test_audit_rejected_over_four():
    r = run([m(orders=[{"qty": 0}] * 5 + [{"qty": 1}])], 0.1)
    assert r == {"total_revenue": 49.5, "status": "AUDIT_REJECTED"}

def test_exactly_four_rejections_not_audit():
    r = run([m(orders=[{"qty": 0}] * 4 + [{"qty": 1}])])
    assert r["status"] == "COMPLETED"

def test_zero_sales_status():
    assert run([m(orders=[{"qty": 0}])])["status"] == "ZERO_SALES"


# ---- monitor_gate_flow ----
def test_gate_no_data():
    assert monitor_gate_flow([]) == "NO_DATA"
    assert monitor_gate_flow(None) == "NO_DATA"

def test_gate_overflow():
    assert monitor_gate_flow([[10, 60, 70]]) == "OVERFLOW"

def test_gate_streak_reset_then_normal():
    assert monitor_gate_flow([[60, 10, 60, 10]]) == "FLOW_NORMAL"

def test_gate_single_high_and_empty_stream():
    assert monitor_gate_flow([[], [51]]) == "FLOW_NORMAL"

def test_gate_overflow_in_second_stream():
    assert monitor_gate_flow([[10, 20], [55, 55]]) == "OVERFLOW"

def test_gate_boundary_50_not_congested():
    assert monitor_gate_flow([[50, 50, 50]]) == "FLOW_NORMAL"


@pytest.mark.parametrize("manifests,tax,expected", [
    ([{"is_confirmed": True, "orders": [{"qty": 1}]}], 0.0,
     {"total_revenue": 45.0, "status": "COMPLETED"}),
    ([m("vip", [{"qty": 1, "promo": "FRAUD_RISK"}]), m(orders=[{"qty": 1}])], 0.0,
     {"total_revenue": 45.0, "status": "COMPLETED"}),
    ([m(orders=[{"qty": 0}] * 4)], 0.0,
     {"total_revenue": 0.0, "status": "ZERO_SALES"}),
    ([m(orders=[{"qty": 0}] * 6)], 0.0,
     {"total_revenue": 0.0, "status": "AUDIT_REJECTED"}),
])
def test_complete_boundary_results(manifests, tax, expected):
    # Default general seat = 45; VIP fraud cancels only its own manifest.
    assert process_ticket_manifest(manifests, tax) == expected


@pytest.mark.parametrize("streams,expected", [
    ([[]], "FLOW_NORMAL"),
    ([[60], [60]], "FLOW_NORMAL"),
    ([[60, 50, 60]], "FLOW_NORMAL"),
])
def test_streak_boundaries(streams, expected):
    # Streak resets at rate 50 and at the start of each new stream.
    assert monitor_gate_flow(streams) == expected
