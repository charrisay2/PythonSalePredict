# Nền tảng Dự báo Nhu cầu Bán hàng có AI Giải thích Kế hoạch

Sản phẩm web hoàn chỉnh (không phải notebook/CLI) cho bài toán **dự báo nhu cầu bán hàng**
theo khu vực, mùa vụ, kênh bán và chương trình khuyến mãi, kết hợp **AI giải thích kết quả**
cho người vận hành.

- **Lĩnh vực:** Data + AI — Demand Forecasting
- **Hướng tiếp cận:** Time Series + Machine Learning + AI Explanation
- **Công nghệ:** Python, scikit-learn / Prophet, PostgreSQL, FastAPI, Streamlit (Plotly), OpenAI / Claude
- **Toàn bộ hệ thống viết bằng Python**

---

## 1. Tính năng chính

| Nhóm | Chi tiết |
|---|---|
| Dữ liệu | Nạp CSV lịch sử, sinh bộ dữ liệu mẫu có mùa vụ / ngày lễ / khuyến mãi, quản lý sản phẩm – khu vực – kênh bán – ngày lễ – khuyến mãi – tồn kho |
| Dự báo | Huấn luyện nhiều mô hình: Seasonal Naive, Moving Average, **Prophet**, **Gradient Boosting**, **Random Forest**, SARIMA |
| Đánh giá | Backtest rolling-origin, hiển thị **MAPE, sMAPE, RMSE, MAE, Bias, độ phủ khoảng tin cậy** và **xếp hạng mô hình** |
| AI giải thích | Tóm tắt lý do nhu cầu tăng/giảm (xu hướng, mùa vụ, ngày lễ, khuyến mãi) và **gợi ý hành động** điều chỉnh tồn kho / chạy khuyến mãi — chỉ dựa trên số liệu và forecast đã tính |
| Dashboard | KPI doanh thu, sản lượng, độ chính xác dự báo, nhu cầu dự báo, cảnh báo đang mở, biểu đồ tháng và top sản phẩm |
| Scenario planning | Mô phỏng what-if: thay đổi khuyến mãi, giá bán, dịch chuyển nhu cầu, thời gian chờ, tồn kho an toàn |
| Cảnh báo | Điểm rủi ro mất hàng theo sản phẩm / khu vực, khuyến nghị đặt hàng lại |
| Báo cáo | Xuất **Excel (.xlsx)**, **PDF**, **CSV** |
| Người dùng | Đăng nhập JWT, phân quyền 3 vai trò (admin / analyst / viewer), quản lý người dùng |

---

## 2. Kiến trúc

```
Streamlit Frontend (Python)  ──HTTPS/JWT──▶  FastAPI Backend (Python)
  9 trang, Plotly                              Services · ML · AI
                                                      │
                                          SQLAlchemy + PostgreSQL (Neon)
```

- **Frontend:** Streamlit đa trang + Plotly, gọi REST API qua `components/api_client.py`.
- **Backend:** FastAPI chia router theo nhóm (`auth`, `users`, `data`, `forecast`, `scenario`, `alerts`, `reports`, `ai`, `dashboard`).
- **ML:** `app/ml/` gồm `features`, `models`, `metrics`, `backtest`, `decomposition`, `registry`.
- **AI:** `app/ai/` gồm `providers` (OpenAI / Anthropic), `prompts`, `fallback`, `explainer`.
- **CSDL:** PostgreSQL khi triển khai; SQLite cho môi trường dev để chạy ngay.

### Cấu trúc thư mục

```
backend/app/
├── core/        config · constants · security · deps · utils
├── db/          base · session · init_db
├── models/      user · catalog · sales · forecasting · ops
├── schemas/     pydantic request/response
├── api/routers/ auth · users · data · forecast · scenario · alerts · reports · ai · dashboard
├── services/    forecasting · scenario · inventory · report · dashboard · sample_data · data_ingest
├── ml/          base · features · models · metrics · backtest · decomposition · registry
└── ai/          prompts · providers · fallback · explainer

frontend/
├── app.py            # Trang chủ + đăng nhập
├── pages/            # 9 trang chức năng
└── components/       # api_client · auth · charts · styles · helpers
```

---

## 3. Chạy nhanh trên máy (local)

### Bước 1 — Cài đặt

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r backend/requirements.txt
pip install -r frontend/requirements.txt
```

### Bước 2 — Cấu hình

```bash
cp .env.example .env
```

Mặc định `.env` dùng SQLite nên chạy được ngay. Muốn dùng PostgreSQL, đổi `DATABASE_URL`:

```
DATABASE_URL=postgresql+psycopg2://user:password@localhost:5432/demand_forecast
```

### Bước 3 — Khởi tạo CSDL + sinh dữ liệu mẫu

```bash
python scripts/seed_data.py
```

Kết quả: tạo bảng, tài khoản admin (`admin@example.com` / `Admin@12345`) và ~65.000 dòng bán hàng mẫu.

### Bước 4 — Chạy backend

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

- API docs: <http://localhost:8000/docs>
- Health check: <http://localhost:8000/health>

### Bước 5 — Chạy frontend

```bash
cd frontend
streamlit run app.py
```

Mở <http://localhost:8501> và đăng nhập bằng `admin@example.com` / `Admin@12345`.

### Chạy bằng Docker (có PostgreSQL)

```bash
docker compose up --build
```

- Frontend: <http://localhost:8501>
- API: <http://localhost:8000/docs>

---

## 4. Triển khai online (bắt buộc có URL)

| Thành phần | Nền tảng | Ghi chú |
|---|---|---|
| PostgreSQL | **Neon** (neon.tech) | Tạo project, lấy connection string |
| Backend (FastAPI) | **Render** | Dùng `render.yaml` hoặc tạo Web Service thủ công, root dir `backend` |
| Frontend (Streamlit) | **Streamlit Community Cloud** | Trỏ tới repo, main file `frontend/app.py` |

### Biến môi trường cho backend trên Render

```
DATABASE_URL=postgresql+psycopg2://<user>:<pass>@<host>/<db>?sslmode=require
SECRET_KEY=<chuoi ngau nhien dai>
ENVIRONMENT=production
BACKEND_CORS_ORIGINS=https://<ten-app>.streamlit.app
FIRST_ADMIN_EMAIL=admin@<domain-cua-ban>
FIRST_ADMIN_PASSWORD=<mat-khau-manh>
LLM_PROVIDER=none            # hoặc openai / anthropic
OPENAI_API_KEY=...           # nếu dùng OpenAI
ANTHROPIC_API_KEY=...        # nếu dùng Claude
```

Lệnh khởi động trên Render:

```bash
python -m app.db.init_db && uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

### Cấu hình frontend trên Streamlit Cloud

Trong **Settings → Secrets** của app Streamlit, thêm:

```toml
API_BASE_URL = "https://<ten-api>.onrender.com"
```

> Lưu ý: gói miễn phí của Render sẽ "ngủ" sau ~15 phút không dùng. Lần truy cập đầu tiên
> có thể chậm 30–60 giây. Có thể dùng dịch vụ warm-up hoặc nâng cấp gói.

---

## 5. Bật AI giải thích thật (OpenAI / Claude)

Mặc định hệ thống chạy **fallback rule-based** (vẫn đầy đủ chức năng, vẫn dựa trên số liệu).
Để bật LLM:

```
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

hoặc

```
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-3-5-sonnet-latest
```

### Cơ chế chống "AI bịa số liệu"

1. **Prompt ràng buộc:** system prompt cấm sử dụng số liệu ngoài khối JSON được cung cấp.
2. **Grounding:** chỉ truyền vào metrics, drivers, forecast summary, kế hoạch tồn kho, promo/holiday sắp tới.
3. **Hậu kiểm tự động:** mỗi con số trong câu trả lời được đối chiếu với tập số liệu gốc; số nào không khớp sẽ bị ghi vào `warnings`.
4. **Cache theo `prompt_hash`** để tiết kiệm chi phí và tăng tốc.
5. **Fallback rule-based** đảm bảo sản phẩm luôn hoạt động khi thiếu API key hoặc LLM lỗi.

---

## 6. API chính

| Nhóm | Endpoint |
|---|---|
| Xác thực | `POST /api/auth/login`, `GET /api/auth/me`, `POST /api/auth/change-password` |
| Người dùng | `GET/POST/PATCH /api/users`, `POST /api/users/{id}/reset-password`, `DELETE /api/users/{id}` |
| Dữ liệu | `POST /api/data/upload`, `POST /api/data/generate-sample`, `GET /api/data/stats`, `GET /api/data/sales`, CRUD sản phẩm / khu vực / kênh / ngày lễ / khuyến mãi, `GET/POST /api/data/inventory` |
| Dự báo | `GET /api/forecast/models`, `POST /api/forecast/train`, `POST /api/forecast/compare`, `GET /api/forecast/runs/{id}/result`, `GET /api/forecast/runs/{id}/leaderboard` |
| Scenario | `POST /api/scenario`, `GET /api/scenario/{id}` |
| Cảnh báo | `GET /api/alerts`, `POST /api/alerts/recompute`, `PATCH /api/alerts/{id}/ack` |
| AI | `POST /api/ai/explain`, `GET /api/ai/status`, `GET /api/ai/context/{run_id}` |
| Báo cáo | `GET /api/reports/runs/{run_id}/export?format=xlsx|pdf|csv` |
| Dashboard | `GET /api/dashboard/summary` |

---

## 7. Phân quyền

| Vai trò | Quyền |
|---|---|
| `viewer` | Xem dashboard, dự báo, so sánh, AI insights, cảnh báo, tải báo cáo |
| `analyst` | Tất cả quyền của viewer + nạp dữ liệu, sinh dữ liệu mẫu, chạy dự báo, tạo kịch bản, tính lại cảnh báo |
| `admin` | Tất cả quyền của analyst + quản lý người dùng, phân quyền |

Backend enforce quyền bằng dependency `require_role(...)`; frontend ẩn / chặn trang theo vai trò.

---

## 8. Kiểm thử

```bash
pytest tests -q
```

Bộ test gồm:

- `tests/test_metrics.py` — kiểm thử công thức MAPE / sMAPE / RMSE / MAE / Bias / coverage.
- `tests/test_ai_grounding.py` — kiểm thử cơ chế hậu kiểm số liệu của AI (không cho phép bịa số).
- `tests/test_api_flow.py` — luồng end-to-end: đăng nhập → phân quyền → sinh dữ liệu → huấn luyện → so sánh mô hình → AI giải thích → scenario → cảnh báo → xuất báo cáo.

---

## 9. Ghi chú kỹ thuật

- **Độ chi tiết dự báo:** `total`, `product`, `region`, `channel`, `product_region`.
- **Backtest:** rolling-origin, số fold và độ dài test cấu hình được từ giao diện.
- **Chạy nền:** huấn luyện được đẩy sang `BackgroundTasks`, giao diện poll trạng thái nên không bị treo.
- **Mô hình tùy chọn:** nếu `prophet` hoặc `statsmodels` chưa cài, hệ thống tự báo "không khả dụng" và vẫn chạy các mô hình còn lại.
- **JSONB:** dùng `JSON` có variant `JSONB` trên PostgreSQL, `JSON` trên SQLite.
- **Giới hạn:** tối đa 60 chuỗi cho một lần dự báo (báo lỗi rõ ràng nếu vượt).
