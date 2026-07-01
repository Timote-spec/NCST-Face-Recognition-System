import numpy as np
from fastapi import APIRouter, HTTPException, UploadFile, File, Form

from app.config import settings
from app.database import get_db_connection, pst_now, pst_str
from app.schemas import AttendanceLogResponse
from app.services.face_service import FaceService

router = APIRouter()
face_service = FaceService()


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


@router.post("/verify", response_model=AttendanceLogResponse)
async def verify_attendance(
    device_id: str = Form(...),
    image: UploadFile = File(...),
):
    image_bytes = await image.read()
    try:
        query_emb = await face_service.extract_embedding(image_bytes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    query_vec = np.array(query_emb, dtype=np.float32)

    conn = get_db_connection()
    rows = conn.execute(
        """SELECT user_id, first_name, last_name, face_embedding
             FROM registrants
            WHERE face_embedding IS NOT NULL AND status = 'ACTIVE'"""
    ).fetchall()

    if not rows:
        raise HTTPException(status_code=404, detail="No active registrants found")

    best_match_id = None
    best_name = None
    best_sim = -1.0

    for row in rows:
        stored_vec = np.frombuffer(row["face_embedding"], dtype=np.float32)
        sim = _cosine_similarity(query_vec, stored_vec)
        if sim > best_sim:
            best_sim = sim
            best_match_id = row["user_id"]
            best_name = f"{row['first_name']} {row['last_name']}"

    if best_match_id is None or best_sim < settings.matching_threshold:
        raise HTTPException(
            status_code=401,
            detail=f"Match not found (highest similarity: {best_sim:.2f})",
        )

    now = pst_now()
    today_start = now.strftime("%Y-%m-%d 00:00:00")
    today_end = now.strftime("%Y-%m-%d 23:59:59")

    already = conn.execute(
        """SELECT 1 FROM attendance_logs
            WHERE user_id = ? AND logged_at >= ? AND logged_at <= ?""",
        (best_match_id, today_start, today_end),
    ).fetchone()

    if already:
        raise HTTPException(
            status_code=400,
            detail="Already logged in for today.",
        )

    now_str = pst_str(now)
    cur = conn.execute(
        "INSERT INTO attendance_logs (user_id, device_id, logged_at) VALUES (?, ?, ?)",
        (best_match_id, device_id, now_str),
    )
    conn.commit()

    record = conn.execute(
        """SELECT a.user_id,
                  r.first_name || ' ' || r.last_name AS user_name,
                  a.logged_at,
                  a.device_id
             FROM attendance_logs a
             JOIN registrants r ON r.user_id = a.user_id
            WHERE a.log_id = ?""",
        (cur.lastrowid,),
    ).fetchone()

    return AttendanceLogResponse(
        user_id=record["user_id"],
        user_name=record["user_name"],
        logged_at=record["logged_at"],
        device_id=record["device_id"],
    )
