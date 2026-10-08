"""Dependencies dùng chung: xác thực, phân quyền, session CSDL."""

from __future__ import annotations

from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.constants import ROLE_ADMIN, ROLE_ANALYST, ROLE_ORDER, ROLE_VIEWER
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import User

bearer_scheme = HTTPBearer(auto_error=False, description="JWT access token (Bearer)")

DbSession = Annotated[Session, Depends(get_db)]


def _unauthorized(detail: str = "Phiên đăng nhập không hợp lệ hoặc đã hết hạn") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or not credentials.credentials:
        raise _unauthorized("Thiếu token xác thực")
    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.ExpiredSignatureError as exc:
        raise _unauthorized("Token đã hết hạn, hãy đăng nhập lại") from exc
    except jwt.PyJWTError as exc:
        raise _unauthorized() from exc

    subject = payload.get("sub")
    if subject is None:
        raise _unauthorized()

    try:
        user_id = int(subject)
    except (TypeError, ValueError) as exc:
        raise _unauthorized() from exc

    user = db.get(User, user_id)
    if user is None:
        raise _unauthorized("Tài khoản không tồn tại")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tài khoản đã bị khóa")
    return user


def require_role(minimum_role: str):
    def _dependency(user: User = Depends(get_current_user)) -> User:
        if ROLE_ORDER.get(user.role, -1) < ROLE_ORDER.get(minimum_role, 99):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Cần quyền '{minimum_role}' trở lên để thực hiện hành động này",
            )
        return user

    return _dependency


CurrentUser = Annotated[User, Depends(get_current_user)]
ViewerUser = Annotated[User, Depends(require_role(ROLE_VIEWER))]
AnalystUser = Annotated[User, Depends(require_role(ROLE_ANALYST))]
AdminUser = Annotated[User, Depends(require_role(ROLE_ADMIN))]
