"""
Integration tests for NCST Face Recognition Attendance System.
Tests API endpoints, SQLite + NumPy pipeline, and cosine similarity.
"""

import io
import os
import sys
import sqlite3
import urllib.request
from pathlib import Path

import numpy as np
import requests

API_BASE = "http://localhost:8000"

PROJECT_ROOT = Path(__file__).parent
TEST_DB = PROJECT_ROOT / "app" / "attendance.db"


def _db_execute(sql, params=()):
    conn = sqlite3.connect(str(TEST_DB))
    conn.row_factory = sqlite3.Row
    cur = conn.execute(sql, params)
    conn.commit()
    rows = cur.fetchall()
    conn.close()
    return rows


def _make_multipart(fields, file_field, file_bytes, filename="test.jpg"):
    boundary = b"----TestBoundary123"
    body = b""
    for key, value in fields.items():
        body += b"--" + boundary + b"\r\n"
        body += f'Content-Disposition: form-data; name="{key}"\r\n'.encode()
        body += b"\r\n"
        body += str(value).encode() + b"\r\n"
    body += b"--" + boundary + b"\r\n"
    body += f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'.encode()
    body += b"Content-Type: image/jpeg\r\n\r\n"
    body += file_bytes + b"\r\n"
    body += b"--" + boundary + b"--\r\n"
    return body, boundary


# ── Tests ──────────────────────────────────────────────────────────


def test_health():
    resp = requests.get(f"{API_BASE}/health", timeout=10)
    assert resp.status_code == 200, f"health failed: {resp.status_code}"
    data = resp.json()
    assert data == {"status": "ok"}, f"unexpected health response: {data}"
    print("[PASS] GET /health -> 200")


def test_register_no_face():
    noise = os.urandom(2048)
    body, boundary = _make_multipart(
        {"student_id": "TEST001", "first_name": "Test", "last_name": "User", "course_section": "CS-A"},
        "image", noise,
    )
    resp = requests.post(
        f"{API_BASE}/api/v1/register",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary.decode()}"},
        timeout=10,
    )
    assert resp.status_code == 400, f"expected 400 for no-face image, got {resp.status_code}"
    detail = resp.json()["detail"]
    assert "No face detected" in detail, f"unexpected detail: {detail}"
    print("[PASS] POST /api/v1/register (no-face image) -> 400")


def test_cosine_similarity():
    a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    b = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    assert np.isclose(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)), 1.0)
    print("[PASS] Cosine similarity identical vectors -> 1.0")

    c = np.array([-1.0, 0.0, 0.0], dtype=np.float32)
    sim = float(np.dot(a, c) / (np.linalg.norm(a) * np.linalg.norm(c)))
    assert np.isclose(sim, -1.0), f"expected -1.0, got {sim}"
    print("[PASS] Cosine similarity opposite vectors -> -1.0")

    d = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    sim = float(np.dot(a, d) / (np.linalg.norm(a) * np.linalg.norm(d)))
    assert np.isclose(sim, 0.0, atol=1e-7), f"expected ~0.0, got {sim}"
    print("[PASS] Cosine similarity orthogonal vectors -> 0.0")


def test_sqlite_numpy_roundtrip():
    original = np.array([0.5, -1.2, 3.14, 2.71], dtype=np.float32)
    blob = original.tobytes()
    restored = np.frombuffer(blob, dtype=np.float32)
    assert np.array_equal(original, restored), "NumPy roundtrip mismatch"
    print("[PASS] NumPy float32 array -> tobytes() -> frombuffer() roundtrip OK")


def test_db_insert_and_query():
    student_id = "TSTDB001"
    _db_execute("DELETE FROM students WHERE student_id = ?", (student_id,))

    emb = np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32)
    _db_execute(
        "INSERT INTO students (student_id, first_name, last_name, course_section, face_embedding) VALUES (?, ?, ?, ?, ?)",
        (student_id, "DB", "Test", "SEC-B", emb.tobytes()),
    )

    rows = _db_execute("SELECT student_id, first_name, last_name FROM students WHERE student_id = ?", (student_id,))
    assert len(rows) == 1, f"expected 1 row, got {len(rows)}"
    assert rows[0]["student_id"] == student_id
    print("[PASS] SQLite INSERT + SELECT roundtrip OK")

    blob_row = _db_execute("SELECT face_embedding FROM students WHERE student_id = ?", (student_id,))
    restored = np.frombuffer(blob_row[0]["face_embedding"], dtype=np.float32)
    assert np.array_equal(emb, restored), "Retrieved embedding differs from original"
    print("[PASS] SQLite BLOB insert + numpy restore OK")

    _db_execute("DELETE FROM students WHERE student_id = ?", (student_id,))


def test_cosine_matching_logic():
    student_id_a = "TSTMAT01"
    student_id_b = "TSTMAT02"
    for sid in (student_id_a, student_id_b):
        _db_execute("DELETE FROM students WHERE student_id = ?", (sid,))

    emb_a = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    emb_b = np.array([0.9, 0.1, 0.0, 0.0], dtype=np.float32)
    _db_execute(
        "INSERT INTO students (student_id, first_name, last_name, course_section, face_embedding) VALUES (?, ?, ?, ?, ?)",
        (student_id_a, "Match", "One", "CS-A", emb_a.tobytes()),
    )
    _db_execute(
        "INSERT INTO students (student_id, first_name, last_name, course_section, face_embedding) VALUES (?, ?, ?, ?, ?)",
        (student_id_b, "Match", "Two", "CS-B", emb_b.tobytes()),
    )

    query = np.array([0.95, -0.05, 0.0, 0.0], dtype=np.float32)
    rows = _db_execute("SELECT student_id, first_name, last_name, face_embedding FROM students")

    best_id, best_name, best_sim = None, None, -1.0
    for row in rows:
        stored = np.frombuffer(row["face_embedding"], dtype=np.float32)
        sim = float(np.dot(query, stored) / (np.linalg.norm(query) * np.linalg.norm(stored)))
        if sim > best_sim:
            best_sim = sim
            best_id = row["student_id"]
            best_name = f"{row['first_name']} {row['last_name']}"

    assert best_id == student_id_a, f"expected {student_id_a}, got {best_id}"
    assert best_sim >= 0.65, f"similarity {best_sim:.4f} below threshold 0.65"
    print(f"[PASS] Cosine matching: {best_name} ({best_id}) @ {best_sim:.4f} (above 0.65 threshold)")

    query_noise = np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float32)
    best_sim_noise = -1.0
    for row in rows:
        stored = np.frombuffer(row["face_embedding"], dtype=np.float32)
        sim = float(np.dot(query_noise, stored) / (np.linalg.norm(query_noise) * np.linalg.norm(stored)))
        if sim > best_sim_noise:
            best_sim_noise = sim

    assert best_sim_noise < 0.65, f"non-matching similarity {best_sim_noise:.4f} exceeded threshold"
    print(f"[PASS] Non-matching rejected: similarity {best_sim_noise:.4f} (below 0.65)")

    for sid in (student_id_a, student_id_b):
        _db_execute("DELETE FROM students WHERE student_id = ?", (sid,))


def test_verify_no_registered_students():
    _db_execute("DELETE FROM students")
    noise = os.urandom(2048)
    body, boundary = _make_multipart(
        {"device_id": "CAM-01"},
        "image", noise,
    )
    resp = requests.post(
        f"{API_BASE}/api/v1/verify",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary.decode()}"},
        timeout=10,
    )
    assert resp.status_code in (400, 401, 404), f"unexpected status: {resp.status_code}"
    print(f"[PASS] POST /api/v1/verify (no students) -> {resp.status_code}")


# ── Setup / Teardown ───────────────────────────────────────────────


def cleanup():
    for sid in ("TEST001", "TSTDB001", "TSTMAT01", "TSTMAT02"):
        _db_execute("DELETE FROM students WHERE student_id = ?", (sid,))
    _db_execute("DELETE FROM attendance_logs")


# ── Runner ─────────────────────────────────────────────────────────


if __name__ == "__main__":
    tests = [
        ("Health check", test_health),
        ("Cosine similarity computation", test_cosine_similarity),
        ("NumPy blob roundtrip", test_sqlite_numpy_roundtrip),
        ("SQLite insert + select", test_db_insert_and_query),
        ("Cosine matching logic", test_cosine_matching_logic),
        ("Register endpoint (no-face)", test_register_no_face),
        ("Verify endpoint (no students)", test_verify_no_registered_students),
    ]

    passed = 0
    failed = 0

    try:
        cleanup()
    except Exception:
        pass

    for name, fn in tests:
        try:
            fn()
            passed += 1
        except Exception as e:
            print(f"[FAIL] {name}: {e}")
            failed += 1

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed, {len(tests)} total")

    try:
        cleanup()
    except Exception:
        pass

    sys.exit(1 if failed else 0)
