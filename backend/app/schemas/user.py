"""Pydantic schema cho người dùng và xác thực."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.constants import ALL_ROLES, ROLE_VIEWER

EMAIL_RE = r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$"

Email = Annotated[str, Field(pattern=EMAIL_RE, max_length=255)]


class UserBase(BaseModel):
    email: Email
    full_name: str = ""
    role: str = ROLE_VIEWER

    @field_validator("role")
    @classmethod
    def _validate_role(cls, value: str) -> str:
        if value not in ALL_ROLES:
            raise ValueError(f"role phải thuộc {ALL_ROLES}")
        return value


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)


class UserUpdate(BaseModel):
    full_name: str | None = None
    role: str | None = None
    is_active: bool | None = None

    @field_validator("role")
    @classmethod
    def _validate_role(cls, value: str | None) -> str | None:
        if value is not None and value not in ALL_ROLES:
            raise ValueError(f"role phải thuộc {ALL_ROLES}")
        return value


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class UserOut(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut
