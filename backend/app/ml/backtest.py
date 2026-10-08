"""Backtesting theo kiểu rolling-origin để đánh giá sai số mô hình."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.ml.metrics import evaluate
from app.ml.registry import build_forecaster

MIN_TRAIN_POINTS = 90


def rolling_origin_backtest(
    model_name: str,
    frame: pd.DataFrame,
    n_folds: int = 3,
    test_size: int = 28,
    min_train: int = MIN_TRAIN_POINTS,
) -> dict:
    """Cắt chuỗi thành nhiều fold, huấn luyện trên quá khứ và dự báo `test_size` điểm.

    `frame` phải có cột: ds (datetime), y, và các regressor (nếu có).
    """
    total = len(frame)
    if total <= min_train + test_size:
        raise ValueError(
            f"Cần ít nhất {min_train + test_size} điểm dữ liệu để backtest, hiện có {total}"
        )

    max_folds = max(1, (total - min_train) // test_size)
    folds = int(min(n_folds, max_folds))

    y_true_all: list[float] = []
    y_pred_all: list[float] = []
    lower_all: list[float] = []
    upper_all: list[float] = []
    fold_details: list[dict] = []

    for fold in range(folds):
        test_start = total - test_size * (folds - fold)
        test_end = test_start + test_size
        if test_start < min_train:
            continue

        train = frame.iloc[:test_start].reset_index(drop=True)
        test = frame.iloc[test_start:test_end].reset_index(drop=True)

        forecaster = build_forecaster(model_name)
        forecaster.fit(train, test)
        output = forecaster.predict()

        fold_metrics = evaluate(
            test["y"].to_numpy(dtype=float),
            output.yhat,
            output.lower,
            output.upper,
        )
        fold_details.append(
            {
                "fold": fold + 1,
                "train_end": str(pd.to_datetime(train["ds"].iloc[-1]).date()),
                "test_start": str(pd.to_datetime(test["ds"].iloc[0]).date()),
                "test_end": str(pd.to_datetime(test["ds"].iloc[-1]).date()),
                **fold_metrics,
            }
        )

        y_true_all.extend(test["y"].to_numpy(dtype=float).tolist())
        y_pred_all.extend(np.asarray(output.yhat, dtype=float).tolist())
        lower_all.extend(np.asarray(output.lower, dtype=float).tolist())
        upper_all.extend(np.asarray(output.upper, dtype=float).tolist())

    if not y_true_all:
        raise ValueError("Không thể tạo fold backtest nào (dữ liệu quá ngắn)")

    overall = evaluate(
        np.asarray(y_true_all, dtype=float),
        np.asarray(y_pred_all, dtype=float),
        np.asarray(lower_all, dtype=float),
        np.asarray(upper_all, dtype=float),
    )
    overall["folds"] = fold_details
    return overall
