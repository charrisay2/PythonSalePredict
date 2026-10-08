"""Nhập dữ liệu bán hàng lịch sử từ file CSV."""

from __future__ import annotations

import io

import pandas as pd
from sqlalchemy import insert
from sqlalchemy.orm import Session

from app.core.utils import safe_round
from app.models import Channel, Product, Region, Sale

COLUMN_ALIASES: dict[str, set[str]] = {
    "sale_date": {"sale_date", "date", "ngay", "ngay_ban", "ds", "order_date", "period", "ngày", "ngày_bán"},
    "sku": {"sku", "product_code", "ma_sp", "ma_san_pham", "product", "san_pham", "item", "mã_sp", "mã_sản_phẩm", "sản_phẩm"},
    "region": {"region", "khu_vuc", "vung", "area", "region_name", "khu_vực", "vùng"},
    "channel": {"channel", "kenh", "kenh_ban", "channel_name", "sales_channel", "kênh", "kênh_bán"},
    "quantity": {"quantity", "qty", "so_luong", "units", "demand", "sales", "quantity_sold", "số_lượng"},
    "unit_price": {"unit_price", "price", "gia", "gia_ban", "don_gia", "giá", "giá_bán", "đơn_giá"},
    "discount_pct": {"discount_pct", "discount", "chiet_khau", "giam_gia", "promo_pct", "chiết_khấu", "giảm_giá"},
    "revenue": {"revenue", "doanh_thu", "amount", "total"},
    "is_holiday": {"is_holiday", "holiday", "ngay_le", "ngày_lễ"},
}

REQUIRED_COLUMNS = ("sale_date", "quantity")

DEFAULT_REGION = ("Mặc định", "DEF")
DEFAULT_CHANNEL = ("Mặc định", "DEF")
DEFAULT_PRODUCT = ("GEN-000", "Sản phẩm chung", "General")


def _normalise(name: str) -> str:
    return str(name).strip().lower().replace(" ", "_").replace("-", "_")


def _map_columns(columns) -> dict[str, str]:
    mapping: dict[str, str] = {}
    normalised = {_normalise(column): column for column in columns}
    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in normalised:
                mapping[canonical] = normalised[alias]
                break
    return mapping


def _get_or_create_region(db: Session, cache: dict, key: str) -> Region:
    key = (key or DEFAULT_REGION[0]).strip() or DEFAULT_REGION[0]
    if key in cache:
        return cache[key]
    region = db.query(Region).filter(Region.name == key).first()
    if region is None:
        code = f"R{abs(hash(key)) % 100000:05d}"
        region = Region(name=key, code=code, demand_factor=1.0)
        db.add(region)
        db.flush()
    cache[key] = region
    return region


def _get_or_create_channel(db: Session, cache: dict, key: str) -> Channel:
    key = (key or DEFAULT_CHANNEL[0]).strip() or DEFAULT_CHANNEL[0]
    if key in cache:
        return cache[key]
    channel = db.query(Channel).filter(Channel.name == key).first()
    if channel is None:
        code = f"C{abs(hash(key)) % 100000:05d}"
        channel = Channel(name=key, code=code, demand_factor=1.0)
        db.add(channel)
        db.flush()
    cache[key] = channel
    return channel


def _get_or_create_product(db: Session, cache: dict, key: str, price: float) -> Product:
    key = (key or DEFAULT_PRODUCT[0]).strip() or DEFAULT_PRODUCT[0]
    if key in cache:
        return cache[key]
    product = db.query(Product).filter(Product.sku == key).first()
    if product is None:
        product = Product(
            sku=key,
            name=key,
            category=DEFAULT_PRODUCT[2],
            unit_price=price,
            unit_cost=price * 0.65,
            lead_time_days=7,
            is_active=True,
        )
        db.add(product)
        db.flush()
    cache[key] = product
    return product


def ingest_sales_csv(db: Session, content: bytes) -> dict:
    """Đọc CSV và chèn vào bảng `sales`. Tự động tạo danh mục còn thiếu."""
    errors: list[str] = []
    try:
        frame = pd.read_csv(io.BytesIO(content))
    except Exception as exc:  # noqa: BLE001
        return {
            "rows_received": 0,
            "rows_inserted": 0,
            "rows_skipped": 0,
            "errors": [f"Không đọc được file CSV: {exc}"],
            "date_start": None,
            "date_end": None,
        }

    if frame.empty:
        return {
            "rows_received": 0,
            "rows_inserted": 0,
            "rows_skipped": 0,
            "errors": ["File CSV không có dữ liệu"],
            "date_start": None,
            "date_end": None,
        }

    mapping = _map_columns(frame.columns)
    missing = [column for column in REQUIRED_COLUMNS if column not in mapping]
    if missing:
        return {
            "rows_received": int(len(frame)),
            "rows_inserted": 0,
            "rows_skipped": int(len(frame)),
            "errors": [
                f"Thiếu cột bắt buộc: {missing}. Cột được nhận diện: {sorted(mapping.keys())}. "
                f"Tiêu đề file: {list(frame.columns)[:12]}"
            ],
            "date_start": None,
            "date_end": None,
        }

    rows_received = int(len(frame))
    region_cache: dict = {}
    channel_cache: dict = {}
    product_cache: dict = {}
    records: list[dict] = []
    skipped = 0

    for index, row in frame.iterrows():
        try:
            raw_date = row[mapping["sale_date"]]
            parsed_date = pd.to_datetime(raw_date, errors="coerce")
            if pd.isna(parsed_date):
                skipped += 1
                if len(errors) < 5:
                    errors.append(f"Dòng {index + 2}: ngày không hợp lệ ('{raw_date}')")
                continue

            quantity = float(row[mapping["quantity"]])
            if quantity < 0:
                skipped += 1
                continue

            price = float(row[mapping["unit_price"]]) if "unit_price" in mapping and not pd.isna(row[mapping["unit_price"]]) else 0.0
            discount = float(row[mapping["discount_pct"]]) if "discount_pct" in mapping and not pd.isna(row[mapping["discount_pct"]]) else 0.0
            revenue = (
                float(row[mapping["revenue"]])
                if "revenue" in mapping and not pd.isna(row[mapping["revenue"]])
                else price * quantity
            )
            is_holiday = 0
            if "is_holiday" in mapping and not pd.isna(row[mapping["is_holiday"]]):
                is_holiday = 1 if str(row[mapping["is_holiday"]]).strip().lower() in {"1", "true", "yes", "y"} else 0

            sku = str(row[mapping["sku"]]).strip() if "sku" in mapping and not pd.isna(row[mapping["sku"]]) else DEFAULT_PRODUCT[0]
            region_name = str(row[mapping["region"]]).strip() if "region" in mapping and not pd.isna(row[mapping["region"]]) else DEFAULT_REGION[0]
            channel_name = str(row[mapping["channel"]]).strip() if "channel" in mapping and not pd.isna(row[mapping["channel"]]) else DEFAULT_CHANNEL[0]

            product = _get_or_create_product(db, product_cache, sku, price or 0.0)
            region = _get_or_create_region(db, region_cache, region_name)
            channel = _get_or_create_channel(db, channel_cache, channel_name)

            records.append(
                {
                    "sale_date": parsed_date.strftime("%Y-%m-%d"),
                    "product_id": product.id,
                    "region_id": region.id,
                    "channel_id": channel.id,
                    "promo_id": None,
                    "quantity": safe_round(quantity, 3),
                    "unit_price": safe_round(price, 2),
                    "revenue": safe_round(revenue, 2),
                    "discount_pct": safe_round(discount, 2),
                    "is_holiday": is_holiday,
                }
            )
        except Exception as exc:  # noqa: BLE001
            skipped += 1
            if len(errors) < 5:
                errors.append(f"Dòng {index + 2}: {exc}")

    if not records:
        db.rollback()
        return {
            "rows_received": rows_received,
            "rows_inserted": 0,
            "rows_skipped": skipped,
            "errors": errors or ["Không có dòng nào hợp lệ để chèn"],
            "date_start": None,
            "date_end": None,
        }

    batch_size = 5000
    for start in range(0, len(records), batch_size):
        db.execute(insert(Sale), records[start : start + batch_size])
    db.commit()

    dates = sorted({record["sale_date"] for record in records})
    return {
        "rows_received": rows_received,
        "rows_inserted": len(records),
        "rows_skipped": skipped,
        "errors": errors,
        "date_start": dates[0],
        "date_end": dates[-1],
    }
