"""Khởi tạo CSDL, tạo tài khoản admin và sinh dữ liệu bán hàng mẫu.

Cách dùng (chạy từ thư mục gốc dự án):
    python scripts/seed_data.py
    python scripts/seed_data.py --days 720 --products 10 --reset
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import settings  # noqa: E402
from app.db.init_db import init as init_database  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.services.sample_data import generate_sample_data  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed dữ liệu cho nền tảng dự báo nhu cầu")
    parser.add_argument("--days", type=int, default=540, help="Số ngày dữ liệu lịch sử")
    parser.add_argument("--products", type=int, default=10, help="Số sản phẩm")
    parser.add_argument("--regions", type=int, default=4, help="Số khu vực")
    parser.add_argument("--channels", type=int, default=3, help="Số kênh bán")
    parser.add_argument("--seed", type=int, default=42, help="Seed ngẫu nhiên")
    parser.add_argument(
        "--no-reset",
        action="store_true",
        help="Không xóa dữ liệu cũ (mặc định sẽ xóa để tránh trùng lặp)",
    )
    args = parser.parse_args()

    print(f"[1/2] Khởi tạo CSDL: {settings.resolve_database_url()}")
    init_database()
    print(f"      Admin: {settings.first_admin_email} / {settings.first_admin_password}")

    print("[2/2] Sinh dữ liệu bán hàng mẫu...")
    with SessionLocal() as db:
        stats = generate_sample_data(
            db,
            days=args.days,
            products=args.products,
            regions=args.regions,
            channels=args.channels,
            seed=args.seed,
            reset=not args.no_reset,
        )

    print("Hoàn tất. Thống kê dữ liệu đã tạo:")
    for key, value in stats.items():
        print(f"  - {key}: {value}")


if __name__ == "__main__":
    main()
