import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File

from app.config import settings
from app.database import get_db_connection, get_admin_email, log_system_action, pst_str
from app.routes.auth import get_current_admin
from app.schemas import (
    AdminDetailRow,
    AuditLogRow,
    GenericResponse,
    LogRow,
    PendingAdminRow,
    RegistrantListRow,
    UpdateAdminStatusRequest,
    UpdateRegistrantRequest,
    VerifyAdminRequest,
)
from app.email_service import send_account_approved_email
from app.services.face_service import FaceService

router = APIRouter()
face_service = FaceService()


def _require_main_admin(admin_id: str) -> str:
    email = get_admin_email(admin_id)
    if not email or email.strip().lower() != settings.main_admin_email.strip().lower():
        raise HTTPException(
            status_code=403,
            detail="Only the main administrator can perform this action.",
        )
    return email


@router.get("/admin/users/pending", response_model=list[PendingAdminRow])
def list_pending_admins(_admin: str = Depends(get_current_admin)):
    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT admin_id, email, first_name, last_name, approval_status, created_at
        FROM admins
        WHERE approval_status = 'pending'
        ORDER BY created_at ASC
        """
    ).fetchall()

    return [
        PendingAdminRow(
            admin_id=r["admin_id"],
            email=r["email"],
            first_name=r["first_name"],
            last_name=r["last_name"],
            approval_status=r["approval_status"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


@router.post("/admin/users/verify", response_model=GenericResponse)
def verify_pending_admin(
    body: VerifyAdminRequest,
    admin_id: str = Depends(get_current_admin),
):
    action = body.action.strip().lower()
    if action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="Action must be 'approve' or 'reject'")

    conn = get_db_connection()
    row = conn.execute(
        """
        SELECT admin_id, email, first_name, last_name, approval_status
        FROM admins
        WHERE admin_id = ?
        """,
        (body.userId,),
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    if row["approval_status"] != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"User is not pending approval (current status: {row['approval_status']})",
        )

    acting_admin_email = get_admin_email(admin_id)
    if acting_admin_email.strip().lower() != settings.main_admin_email.strip().lower():
        raise HTTPException(
            status_code=403,
            detail="Only the main administrator can approve or reject new admin registrations.",
        )

    if action == "approve":
        conn.execute(
            """
            UPDATE admins
               SET is_approved = 1,
                   approval_status = 'approved'
             WHERE admin_id = ?
            """,
            (body.userId,),
        )
        conn.commit()
        try:
            send_account_approved_email(row["email"], row["first_name"])
        except Exception:
            pass
        log_system_action(
            acting_admin_email,
            "APPROVE_ADMIN",
            f"Approved admin account {row['email']} ({body.userId})",
        )
        return GenericResponse(status="ok", message=f"Account for {row['email']} has been approved.")

    conn.execute(
        """
        UPDATE admins
           SET is_approved = 0,
               approval_status = 'rejected'
         WHERE admin_id = ?
        """,
        (body.userId,),
    )
    conn.commit()
    log_system_action(
        acting_admin_email,
        "REJECT_ADMIN",
        f"Rejected admin account {row['email']} ({body.userId})",
    )
    return GenericResponse(status="ok", message=f"Account for {row['email']} has been rejected.")


@router.get("/admin/admins", response_model=list[AdminDetailRow])
def list_all_admins(_admin: str = Depends(get_current_admin)):
    _require_main_admin(_admin)
    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT admin_id, email, first_name, last_name, approval_status, is_approved, created_at
        FROM admins
        ORDER BY created_at ASC
        """
    ).fetchall()
    return [
        AdminDetailRow(
            admin_id=r["admin_id"],
            email=r["email"],
            first_name=r["first_name"],
            last_name=r["last_name"],
            approval_status=r["approval_status"],
            is_approved=bool(r["is_approved"]),
            created_at=r["created_at"],
        )
        for r in rows
    ]


@router.patch("/admin/admins/{admin_id}/status", response_model=GenericResponse)
def update_admin_status(
    admin_id: str,
    body: UpdateAdminStatusRequest,
    _admin: str = Depends(get_current_admin),
):
    acting_email = _require_main_admin(_admin)
    status = body.approval_status.strip().lower()
    if status not in ("pending", "approved", "rejected", "suspended"):
        raise HTTPException(
            status_code=400,
            detail="Status must be one of: pending, approved, rejected, suspended",
        )

    conn = get_db_connection()
    row = conn.execute(
        "SELECT admin_id, email, approval_status FROM admins WHERE admin_id = ?",
        (admin_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Admin not found")

    if row["email"].strip().lower() == settings.main_admin_email.strip().lower():
        raise HTTPException(
            status_code=403,
            detail="Cannot change the status of the main administrator.",
        )

    is_approved = 1 if status == "approved" else 0
    conn.execute(
        "UPDATE admins SET approval_status = ?, is_approved = ? WHERE admin_id = ?",
        (status, is_approved, admin_id),
    )
    conn.commit()

    log_system_action(
        acting_email,
        "UPDATE_ADMIN_STATUS",
        f"Changed status of admin {row['email']} ({admin_id}) from {row['approval_status']} to {status}",
    )

    return GenericResponse(
        status="ok",
        message=f"Status for {row['email']} updated to '{status}'.",
    )


@router.delete("/admin/admins/{admin_id}", response_model=GenericResponse)
def delete_admin(
    admin_id: str,
    _admin: str = Depends(get_current_admin),
):
    acting_email = _require_main_admin(_admin)

    conn = get_db_connection()
    row = conn.execute(
        "SELECT admin_id, email FROM admins WHERE admin_id = ?",
        (admin_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Admin not found")

    if row["email"].strip().lower() == settings.main_admin_email.strip().lower():
        raise HTTPException(
            status_code=403,
            detail="Cannot delete the main administrator account.",
        )

    conn.execute("DELETE FROM admins WHERE admin_id = ?", (admin_id,))
    conn.commit()

    log_system_action(
        acting_email,
        "DELETE_ADMIN",
        f"Deleted admin account {row['email']} ({admin_id})",
    )

    return GenericResponse(
        status="ok",
        message=f"Admin account {row['email']} has been deleted.",
    )


@router.get("/admin/users", response_model=list[RegistrantListRow])
def list_users(
    role: str | None = Query(None, regex="^(STUDENT|STAFF|FACULTY)$"),
    status: str | None = Query(None, regex="^(ACTIVE|ARCHIVED)$"),
    _admin: str = Depends(get_current_admin),
):
    conn = get_db_connection()
    sql = "SELECT user_id, first_name, last_name, role, department_section, status, created_at FROM registrants WHERE 1=1"
    params = []

    if role:
        sql += " AND role = ?"
        params.append(role)
    if status:
        sql += " AND status = ?"
        params.append(status)

    sql += " ORDER BY created_at DESC"
    rows = conn.execute(sql, params).fetchall()

    return [
        RegistrantListRow(
            user_id=r["user_id"],
            first_name=r["first_name"],
            last_name=r["last_name"],
            role=r["role"],
            department_section=r["department_section"],
            status=r["status"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


@router.put("/admin/users/{user_id}/status", response_model=RegistrantListRow)
def toggle_user_status(
    user_id: str,
    _admin: str = Depends(get_current_admin),
):
    conn = get_db_connection()
    row = conn.execute(
        "SELECT user_id, first_name, last_name, role, department_section, status, created_at FROM registrants WHERE user_id = ?",
        (user_id,),
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    new_status = "ARCHIVED" if row["status"] == "ACTIVE" else "ACTIVE"
    conn.execute("UPDATE registrants SET status = ? WHERE user_id = ?", (new_status, user_id))
    conn.commit()

    admin_email = get_admin_email(_admin)
    log_system_action(
        admin_email,
        "TOGGLE_STATUS",
        f"Changed user {user_id} status from {row['status']} to {new_status}",
    )

    updated = conn.execute(
        "SELECT user_id, first_name, last_name, role, department_section, status, created_at FROM registrants WHERE user_id = ?",
        (user_id,),
    ).fetchone()

    return RegistrantListRow(
        user_id=updated["user_id"],
        first_name=updated["first_name"],
        last_name=updated["last_name"],
        role=updated["role"],
        department_section=updated["department_section"],
        status=updated["status"],
        created_at=updated["created_at"],
    )


@router.get("/admin/logs")
def list_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    search: str | None = Query(None),
    _admin: str = Depends(get_current_admin),
):
    conn = get_db_connection()

    base_sql = """FROM attendance_logs a
                   JOIN registrants r ON r.user_id = a.user_id
                  WHERE 1=1"""
    params = []

    if date_from:
        base_sql += " AND a.logged_at >= ?"
        params.append(date_from)
    if date_to:
        base_sql += " AND a.logged_at <= ?"
        params.append(date_to + " 23:59:59" if len(date_to) == 10 else date_to)
    if search:
        base_sql += " AND (r.first_name LIKE ? OR r.last_name LIKE ? OR r.user_id LIKE ?)"
        like = f"%{search}%"
        params.extend([like, like, like])

    total = conn.execute(f"SELECT COUNT(*) {base_sql}", params).fetchone()[0]

    offset = (page - 1) * page_size
    rows = conn.execute(
        f"""SELECT a.log_id, a.user_id, r.first_name, r.last_name, r.role, r.department_section, a.logged_at, a.device_id
               {base_sql}
            ORDER BY a.logged_at DESC
            LIMIT ? OFFSET ?""",
        params + [page_size, offset],
    ).fetchall()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            LogRow(
                log_id=r["log_id"],
                user_id=r["user_id"],
                first_name=r["first_name"],
                last_name=r["last_name"],
                role=r["role"],
                department_section=r["department_section"],
                logged_at=r["logged_at"],
                device_id=r["device_id"],
            )
            for r in rows
        ],
    }


@router.put("/admin/users/{user_id}", response_model=RegistrantListRow)
def update_registrant(
    user_id: str,
    body: UpdateRegistrantRequest,
    _admin: str = Depends(get_current_admin),
):
    if body.role not in ("STUDENT", "STAFF", "FACULTY"):
        raise HTTPException(status_code=400, detail="Role must be STUDENT, STAFF, or FACULTY")

    conn = get_db_connection()
    row = conn.execute(
        "SELECT user_id, first_name, last_name, role, department_section, status, created_at FROM registrants WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    conn.execute(
        "UPDATE registrants SET first_name = ?, last_name = ?, role = ?, department_section = ? WHERE user_id = ?",
        (body.first_name, body.last_name, body.role, body.department_section, user_id),
    )
    conn.commit()

    admin_email = get_admin_email(_admin)
    log_system_action(
        admin_email,
        "UPDATE_REGISTRANT",
        f"Updated user {user_id}: name={body.first_name} {body.last_name}, role={body.role}, dept={body.department_section}",
    )

    updated = conn.execute(
        "SELECT user_id, first_name, last_name, role, department_section, status, created_at FROM registrants WHERE user_id = ?",
        (user_id,),
    ).fetchone()

    return RegistrantListRow(
        user_id=updated["user_id"],
        first_name=updated["first_name"],
        last_name=updated["last_name"],
        role=updated["role"],
        department_section=updated["department_section"],
        status=updated["status"],
        created_at=updated["created_at"],
    )


@router.post("/admin/users/{user_id}/re-enroll", response_model=GenericResponse)
async def reenroll_registrant(
    user_id: str,
    image: UploadFile = File(...),
    _admin: str = Depends(get_current_admin),
):
    conn = get_db_connection()
    row = conn.execute(
        "SELECT user_id FROM registrants WHERE user_id = ?", (user_id,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    image_bytes = await image.read()
    try:
        embedding = await face_service.extract_embedding(image_bytes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    embedding_blob = np.array(embedding, dtype=np.float32).tobytes()
    conn.execute(
        "UPDATE registrants SET face_embedding = ? WHERE user_id = ?",
        (embedding_blob, user_id),
    )
    conn.commit()

    admin_email = get_admin_email(_admin)
    log_system_action(
        admin_email,
        "RE_ENROLL",
        f"Re-enrolled face embedding for user {user_id}",
    )

    return GenericResponse(status="ok", message=f"Face re-enrolled for {user_id}")


@router.get("/admin/audit-logs")
def list_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    _admin: str = Depends(get_current_admin),
):
    conn = get_db_connection()
    total = conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
    offset = (page - 1) * page_size
    rows = conn.execute(
        "SELECT log_id, admin_email, action, details, logged_at FROM audit_logs ORDER BY logged_at DESC LIMIT ? OFFSET ?",
        (page_size, offset),
    ).fetchall()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            AuditLogRow(
                log_id=r["log_id"],
                admin_email=r["admin_email"],
                action=r["action"],
                details=r["details"],
                logged_at=r["logged_at"],
            )
            for r in rows
        ],
    }
