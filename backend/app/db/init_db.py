"""Khởi tạo CSDL: tạo bảng và tài khoản admin đầu tiên."""

from app.core.config import settings
from app.core.constants import ROLE_ADMIN
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models import User  # noqa: F401  (đăng ký metadata)


def create_tables() -> None:
    Base.metadata.create_all(bind=engine)


def bootstrap_admin() -> bool:
    """Tạo admin đầu tiên nếu chưa tồn tại. Trả về True nếu vừa tạo mới."""
    with SessionLocal() as db:
        existing = db.query(User).filter(User.email == settings.first_admin_email).first()
        if existing:
            return False
        admin = User(
            email=settings.first_admin_email,
            hashed_password=hash_password(settings.first_admin_password),
            full_name=settings.first_admin_name,
            role=ROLE_ADMIN,
            is_active=True,
        )
        db.add(admin)
        db.commit()
        return True


def init() -> None:
    create_tables()
    bootstrap_admin()


if __name__ == "__main__":
    init()
    print(f"Database ready. Admin: {settings.first_admin_email}")
