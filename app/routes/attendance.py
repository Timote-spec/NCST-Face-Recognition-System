import numpy as np
from fastapi import APIRouter, UploadFile, File, Form

from app.config import settings
from app.database import get_db_connection, pst_now, pst_str
from app.schemas import AttendanceLogItem, FaceBbox, FaceResult, VerifyAttendanceResponse
from app.services.face_service import FaceService

router = APIRouter()
face_service = FaceService()


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


@router.post("/verify", response_model=VerifyAttendanceResponse)
async def verify_attendance(
    device_id: str = Form(...),
    image: UploadFile = File(...),
):
    image_bytes = await image.read()
    detected_faces = await face_service.detect_faces(image_bytes)

    conn = get_db_connection()
    registrants = conn.execute(
        """SELECT user_id, first_name, last_name, face_embedding
             FROM registrants
            WHERE face_embedding IS NOT NULL AND status = 'ACTIVE'"""
    ).fetchall()

    now = pst_now()
    today_start = now.strftime("%Y-%m-%d 00:00:00")
    today_end = now.strftime("%Y-%m-%d 23:59:59")
    now_str = pst_str(now)

    faces_result = []
    matched_items = []

    for det in detected_faces:
        query_vec = np.array(det["embedding"], dtype=np.float32)
        best_match_id = None
        best_name = None
        best_sim = -1.0

        for row in registrants:
            stored_vec = np.frombuffer(row["face_embedding"], dtype=np.float32)
            sim = _cosine_similarity(query_vec, stored_vec)
            if sim > best_sim:
                best_sim = sim
                best_match_id = row["user_id"]
                best_name = f"{row['first_name']} {row['last_name']}"

        bbox = FaceBbox(**det["bbox"])

        if best_match_id is None or best_sim < settings.matching_threshold:
            faces_result.append(
                FaceResult(bbox=bbox, user_name="Unknown")
            )
            continue

        already = conn.execute(
            """SELECT a.logged_at, a.device_id
                     FROM attendance_logs a
                    WHERE a.user_id = ? AND a.logged_at >= ? AND a.logged_at <= ?
                    LIMIT 1""",
            (best_match_id, today_start, today_end),
        ).fetchone()

        logged_at = None
        device = None
        face_status = "unknown"
        if best_match_id is not None and best_sim >= settings.matching_threshold:
            if not already:
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

                logged_at = record["logged_at"]
                device = record["device_id"]

                matched_items.append(
                    AttendanceLogItem(
                        user_id=record["user_id"],
                        user_name=record["user_name"],
                        logged_at=record["logged_at"],
                        device_id=record["device_id"],
                        similarity=round(best_sim, 4),
                        status="checked_in",
                    )
                )
                face_status = "checked_in"
            else:
                matched_items.append(
                    AttendanceLogItem(
                        user_id=best_match_id,
                        user_name=best_name,
                        logged_at=already["logged_at"],
                        device_id=already["device_id"],
                        similarity=round(best_sim, 4),
                        status="already_logged",
                    )
                )
                face_status = "already_logged"

        faces_result.append(
            FaceResult(
                bbox=bbox,
                user_name=best_name,
                user_id=best_match_id,
                logged_at=logged_at,
                device_id=device_id,
                similarity=round(best_sim, 4),
                status=face_status,
            )
        )

    return VerifyAttendanceResponse(
        faces=faces_result,
        matched=matched_items,
        unmatched_faces=sum(1 for f in faces_result if f.user_name == "Unknown"),
    )
