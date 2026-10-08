"""Kiểm thử các chỉ số sai số."""

from __future__ import annotations

import numpy as np
import pytest

from app.ml.metrics import accuracy_from_mape, bias, evaluate, mae, mape, ranking_score, rmse, smape


def test_perfect_prediction_gives_zero_error():
    y = [10.0, 20.0, 30.0]
    assert mape(y, y) == 0.0
    assert rmse(y, y) == 0.0
    assert mae(y, y) == 0.0
    assert bias(y, y) == 0.0


def test_mape_matches_manual_computation():
    y_true = [100.0, 200.0]
    y_pred = [110.0, 180.0]
    # |10/100| + |20/200| -> (0.1 + 0.1)/2 = 10%
    assert mape(y_true, y_pred) == pytest.approx(10.0, rel=1e-6)


def test_mape_ignores_zero_actuals():
    assert mape([0.0, 100.0], [5.0, 90.0]) == pytest.approx(10.0, rel=1e-6)


def test_smape_is_bounded():
    value = smape([0.0, 0.0], [10.0, 10.0])
    assert 0.0 <= value <= 200.0


def test_bias_sign_indicates_over_forecast():
    assert bias([100.0], [120.0]) > 0
    assert bias([100.0], [80.0]) < 0


def test_evaluate_returns_all_expected_keys():
    result = evaluate([10, 20, 30], [12, 18, 33], [5, 15, 25], [20, 25, 40])
    for key in ("mape", "smape", "rmse", "mae", "bias", "n_obs", "coverage"):
        assert key in result
    assert result["n_obs"] == 3
    assert 0.0 <= result["coverage"] <= 100.0


def test_ranking_prefers_lower_mape():
    good = {"mape": 5.0, "smape": 6.0}
    bad = {"mape": 25.0, "smape": 22.0}
    assert ranking_score(good) < ranking_score(bad)


def test_accuracy_from_mape_is_clamped():
    assert accuracy_from_mape(0.0) == 100.0
    assert accuracy_from_mape(150.0) == 0.0
    assert accuracy_from_mape(None) is None


def test_handles_numpy_arrays():
    y = np.array([1.0, 2.0, 3.0])
    assert mae(y, y) == 0.0
