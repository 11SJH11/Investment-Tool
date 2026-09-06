from app.backtesting.strategies.reference import EmaCrossReference, OpeningRangeBreakoutReference


def test_ema_reference_risk_management_is_strategy_owned_not_run_parameter():
    keys = {parameter.key for parameter in EmaCrossReference.spec.parameters}
    assert "stop_atr" not in keys
    assert "target_rr" not in keys
    assert "breakeven_trigger_r" not in keys
    assert "partial_trigger_r" not in keys
    assert "trail_atr_multiple" not in keys
    assert EmaCrossReference.STOP_ATR == 1.5
    assert EmaCrossReference.TARGET_RR == 2.0
    assert "Initial stop" in EmaCrossReference.spec.risk_management


def test_orb_reference_target_is_strategy_owned_not_run_parameter():
    keys = {parameter.key for parameter in OpeningRangeBreakoutReference.spec.parameters}
    assert "target_rr" not in keys
    assert OpeningRangeBreakoutReference.TARGET_RR == 2.0
    assert "Initial target" in OpeningRangeBreakoutReference.spec.risk_management
