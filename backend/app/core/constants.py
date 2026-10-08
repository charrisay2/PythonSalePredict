"""Hằng số dùng chung: vai trò, trạng thái, tên mô hình."""

ROLE_ADMIN = "admin"
ROLE_ANALYST = "analyst"
ROLE_VIEWER = "viewer"

ALL_ROLES = (ROLE_ADMIN, ROLE_ANALYST, ROLE_VIEWER)

# Quyền theo vai trò: admin > analyst > viewer
ROLE_ORDER = {ROLE_VIEWER: 0, ROLE_ANALYST: 1, ROLE_ADMIN: 2}

# --- Trạng thái job huấn luyện ---
JOB_PENDING = "pending"
JOB_RUNNING = "running"
JOB_COMPLETED = "completed"
JOB_FAILED = "failed"

# --- Loại cảnh báo ---
ALERT_STOCKOUT = "stockout"
ALERT_OVERSTOCK = "overstock"

# --- Tên mô hình dự báo ---
MODEL_NAIVE = "naive"
MODEL_SEASONAL_NAIVE = "seasonal_naive"
MODEL_MOVING_AVERAGE = "moving_average"
MODEL_PROPHET = "prophet"
MODEL_GRADIENT_BOOSTING = "gradient_boosting"
MODEL_RANDOM_FOREST = "random_forest"
MODEL_SARIMA = "sarima"

ALL_MODELS = (
    MODEL_NAIVE,
    MODEL_SEASONAL_NAIVE,
    MODEL_MOVING_AVERAGE,
    MODEL_PROPHET,
    MODEL_GRADIENT_BOOSTING,
    MODEL_RANDOM_FOREST,
    MODEL_SARIMA,
)

MODEL_LABELS = {
    MODEL_NAIVE: "Naive (kỳ trước)",
    MODEL_SEASONAL_NAIVE: "Seasonal Naive (lag 7)",
    MODEL_MOVING_AVERAGE: "Moving Average (28 kỳ)",
    MODEL_PROPHET: "Prophet (xu hướng + mùa vụ)",
    MODEL_GRADIENT_BOOSTING: "Gradient Boosting (đặc trưng trễ)",
    MODEL_RANDOM_FOREST: "Random Forest (đặc trưng trễ)",
    MODEL_SARIMA: "SARIMA (statsmodels)",
}

DEFAULT_MODELS = (
    MODEL_SEASONAL_NAIVE,
    MODEL_MOVING_AVERAGE,
    MODEL_PROPHET,
    MODEL_GRADIENT_BOOSTING,
    MODEL_RANDOM_FOREST,
)
