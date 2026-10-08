"""Xuất dữ liệu bán hàng từ CSDL ra file CSV mẫu (dùng để thử chức năng upload).

Cách dùng:
    python scripts/export_sample_csv.py
    python scripts/export_sample_csv.py --limit 5000 --output data/sample_sales.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.db.session import SessionLocal  # noqa: E402
from app.models import Channel, Product, Region, Sale  # noqa: E402

HEADER = ["sale_date", "sku", "region", "channel", "quantity", "unit_price", "discount_pct", "revenue", "is_holiday"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Xuất CSV mẫu từ dữ liệu trong CSDL")
    parser.add_argument("--limit", type=int, default=5000, help="Số dòng tối đa")
    parser.add_argument("--output", default="data/sample_sales.csv", help="Đường dẫn file CSV")
    args = parser.parse_args()

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = Path(__file__).resolve().parents[1] / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with SessionLocal() as db:
        products = {item.id: item.sku for item in db.query(Product).all()}
        regions = {item.id: item.name for item in db.query(Region).all()}
        channels = {item.id: item.name for item in db.query(Channel).all()}
        rows = db.query(Sale).order_by(Sale.sale_date.desc()).limit(args.limit).all()

        if not rows:
            print("CSDL chưa có dữ liệu bán hàng. Hãy chạy: python scripts/seed_data.py")
            return

        with output_path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(HEADER)
            for row in rows:
                writer.writerow(
                    [
                        row.sale_date,
                        products.get(row.product_id, "UNKNOWN"),
                        regions.get(row.region_id, "UNKNOWN"),
                        channels.get(row.channel_id, "UNKNOWN"),
                        row.quantity,
                        row.unit_price,
                        row.discount_pct,
                        row.revenue,
                        row.is_holiday,
                    ]
                )

    print(f"Đã xuất {len(rows)} dòng ra {output_path}")


if __name__ == "__main__":
    main()
