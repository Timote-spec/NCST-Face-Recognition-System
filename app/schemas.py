from datetime import datetime
from typing import Optional

from pydantic import BaseModel


# ─── Registrants ───────────────────────────────────────────────────

class RegisterRegistrantRequest(BaseModel):
    user_id: str
    first_name: str
    last_name: str
    role: str
    department_section: str


class RegistrantResponse(BaseModel):
    user_id: str
    first_name: str
    last_name: str
    role: str
    department_section: str
    status: str

    class Config:
        from_attributes = True


class RegistrantListRow(BaseModel):
    user_id: str
    first_name: str
    last_name: str
    role: str
    department_section: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class MarkAttendanceRequest(BaseModel):
    device_id: str


class AttendanceLogResponse(BaseModel):
    user_id: str
    user_name: str
    logged_at: datetime
    device_id: str

    class Config:
        from_attributes = True


class AttendanceLogItem(BaseModel):
    user_id: str
    user_name: str
    logged_at: datetime
    device_id: str
    similarity: float
    status: str = "checked_in"


class FaceBbox(BaseModel):
    x: float
    y: float
    width: float
    height: float


class FaceResult(BaseModel):
    bbox: FaceBbox
    user_name: str
    user_id: str | None = None
    logged_at: datetime | None = None
    device_id: str | None = None
    similarity: float | None = None
    status: str = "unknown"


class VerifyAttendanceResponse(BaseModel):
    faces: list[FaceResult]
    matched: list[AttendanceLogItem]
    unmatched_faces: int


# ─── Auth / Admin ──────────────────────────────────────────────────

class AdminRegisterRequest(BaseModel):
    admin_id: str
    email: str
    password: str
    first_name: str
    last_name: str


class RequestRegistrationOtpRequest(BaseModel):
    email: str


class AdminLoginRequest(BaseModel):
    email: str
    password: str


class AdminResponse(BaseModel):
    admin_id: str
    email: str
    first_name: str
    last_name: str
    created_at: datetime
    is_approved: bool = False
    approval_status: str = "pending"

    class Config:
        from_attributes = True


class PendingAdminRow(BaseModel):
    admin_id: str
    email: str
    first_name: str
    last_name: str
    approval_status: str
    created_at: datetime

    class Config:
        from_attributes = True


class VerifyAdminRequest(BaseModel):
    userId: str
    action: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordTokenRequest(BaseModel):
    token: str
    new_password: str


class RequestOtpRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    email: str
    otp: str
    new_password: str


class GenericResponse(BaseModel):
    status: str
    message: str


class LogRow(BaseModel):
    log_id: int
    user_id: str
    first_name: str
    last_name: str
    role: str
    department_section: str
    logged_at: datetime
    device_id: str

    class Config:
        from_attributes = True


class UpdateRegistrantRequest(BaseModel):
    first_name: str
    last_name: str
    role: str
    department_section: str


class AuditLogRow(BaseModel):
    log_id: int
    admin_email: str | None
    action: str
    details: str | None
    logged_at: datetime

    class Config:
        from_attributes = True


class AdminDetailRow(BaseModel):
    admin_id: str
    email: str
    first_name: str
    last_name: str
    approval_status: str
    is_approved: bool
    created_at: datetime

    class Config:
        from_attributes = True


class UpdateAdminStatusRequest(BaseModel):
    approval_status: str


class PaginatedResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list
