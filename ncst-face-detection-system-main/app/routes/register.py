import numpy as np
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form

from app.config import settings
from app.database import get_db_connection, get_admin_email, log_system_action, pst_str
from app.routes.auth import get_current_admin
from app.schemas import RegistrantResponse
from app.services.face_service import FaceService

router = APIRouter()
face_service = FaceService()


def _maybe_admin(admin_id: str | None = Depends(get_current_admin)) -> str | None:
    if settings.open_enrollment:
        return None
    return admin_id


@router.post("/register", response_model=RegistrantResponse)
async def register_registrant(
    user_id: str = Form(...),
    first_name: str = Form(...),
    last_name: str = Form(...),
    role: str = Form(...),
    department_section: str = Form(...),
    image: UploadFile = File(...),
    _admin: str | None = Depends(_maybe_admin),
):
    if role not in ("STUDENT", "STAFF", "FACULTY"):
        raise HTTPException(status_code=400, detail="Role must be STUDENT, STAFF, or FACULTY")

    image_bytes = await image.read()
    try:
        embedding = await face_service.extract_embedding(image_bytes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    embedding_blob = np.array(embedding, dtype=np.float32).tobytes()

    conn = get_db_connection()
    now_str = pst_str()
    try:
        conn.execute(
            "INSERT INTO registrants (user_id, first_name, last_name, role, department_section, face_embedding, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, first_name, last_name, role, department_section, embedding_blob, now_str),
        )
        conn.commit()
    except Exception as e:
        raise HTTPException(status_code=409, detail=f"Registrant already exists: {e}")

    admin_email = get_admin_email(_admin) if _admin else None
    log_system_action(
        admin_email,
        "REGISTER_USER",
        f"Registered user {user_id} ({first_name} {last_name}) as {role}",
    )

    return RegistrantResponse(
        user_id=user_id,
        first_name=first_name,
        last_name=last_name,
        role=role,
        department_section=department_section,
        status="ACTIVE",
    )
