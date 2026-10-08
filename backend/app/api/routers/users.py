"""Quản lý người dùng (chỉ admin)."""

from fastapi import APIRouter, HTTPException, Query, status

from app.core.deps import AdminUser, CurrentUser, DbSession
from app.core.security import hash_password
from app.models import AuditLog, User
from app.schemas.common import Message
from app.schemas.user import UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/users", tags=["Quản lý người dùng"])


def _get_user(db: DbSession, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
    return user


@router.get("", response_model=list[UserOut], summary="Danh sách người dùng")
def list_users(
    admin: AdminUser,
    db: DbSession,
    q: str | None = Query(default=None, description="Tìm theo email hoặc tên"),
) -> list[UserOut]:
    query = db.query(User)
    if q:
        pattern = f"%{q.strip().lower()}%"
        query = query.filter((User.email.ilike(pattern)) | (User.full_name.ilike(pattern)))
    users = query.order_by(User.created_at.desc()).all()
    return [UserOut.model_validate(user) for user in users]


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED, summary="Tạo người dùng")
def create_user(payload: UserCreate, admin: AdminUser, db: DbSession) -> UserOut:
    email = payload.email.strip().lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="Email đã tồn tại")
    user = User(
        email=email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,
        is_active=True,
    )
    db.add(user)
    db.add(AuditLog(user_id=admin.id, action="create_user", entity="user", detail=email))
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.patch("/{user_id}", response_model=UserOut, summary="Cập nhật người dùng")
def update_user(user_id: int, payload: UserUpdate, admin: AdminUser, db: DbSession) -> UserOut:
    user = _get_user(db, user_id)
    data = payload.model_dump(exclude_unset=True)

    if data.get("role") == "viewer" and user.role == "admin" and user.id == admin.id:
        raise HTTPException(status_code=400, detail="Không thể tự hạ quyền của chính mình")
    if data.get("is_active") is False and user.id == admin.id:
        raise HTTPException(status_code=400, detail="Không thể tự khóa tài khoản của chính mình")

    for field, value in data.items():
        setattr(user, field, value)

    db.add(AuditLog(user_id=admin.id, action="update_user", entity="user", entity_id=user.id, detail=str(data)))
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.post("/{user_id}/reset-password", response_model=Message, summary="Đặt lại mật khẩu")
def reset_password(
    user_id: int,
    admin: AdminUser,
    db: DbSession,
    new_password: str = Query(min_length=8, max_length=128),
) -> Message:
    user = _get_user(db, user_id)
    user.hashed_password = hash_password(new_password)
    db.add(AuditLog(user_id=admin.id, action="reset_password", entity="user", entity_id=user.id))
    db.commit()
    return Message(message=f"Đã đặt lại mật khẩu cho {user.email}")


@router.delete("/{user_id}", response_model=Message, summary="Khóa tài khoản người dùng")
def deactivate_user(user_id: int, admin: AdminUser, db: DbSession) -> Message:
    user = _get_user(db, user_id)
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="Không thể khóa tài khoản của chính mình")
    user.is_active = False
    db.add(AuditLog(user_id=admin.id, action="deactivate_user", entity="user", entity_id=user.id))
    db.commit()
    return Message(message=f"Đã khóa tài khoản {user.email}")
