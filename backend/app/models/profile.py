import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserRole(enum.StrEnum):
    PATIENT = "patient"
    CLINICIAN = "clinician"


class Profile(Base):
    """Application-side identity, keyed by the Supabase auth user id."""

    __tablename__ = "profiles"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    role: Mapped[UserRole | None] = mapped_column(
        Enum(UserRole, name="user_role", values_callable=lambda e: [m.value for m in e])
    )
    display_name: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
