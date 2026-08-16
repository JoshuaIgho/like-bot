import sqlite3
from typing import List
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse
from app.db import get_db_connection
from app.models import JobResponse, LikeRequest

router = APIRouter(prefix="/api", tags=["jobs"])


@router.post("/like")
def create_like_job(req: LikeRequest):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Check account existence and status
        cursor.execute(
            "SELECT id, status FROM accounts WHERE id = ?", (req.account_id,)
        )
        account = cursor.fetchone()
        if not account or account["status"] != "ok":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Account does not exist or status is not 'ok'",
            )

        # Check existing job for url and account_id
        cursor.execute(
            """
            SELECT j.id, j.url, j.account_id, j.status, j.result, j.attempts, j.created_at, j.updated_at, a.username
            FROM jobs j
            JOIN accounts a ON j.account_id = a.id
            WHERE j.url = ? AND j.account_id = ?
            """,
            (req.url, req.account_id),
        )
        existing_job = cursor.fetchone()
        if existing_job:
            job_dict = dict(existing_job)
            job_dict["job_id"] = existing_job["id"]
            job_dict["username"] = existing_job["username"]
            job_dict["account_username"] = existing_job["username"]
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={
                    "detail": "Job already exists",
                    "job_id": existing_job["id"],
                    "job": job_dict,
                },
            )

        # Insert new job
        cursor.execute(
            """
            INSERT INTO jobs (url, account_id, status, attempts)
            VALUES (?, ?, 'pending', 0)
            """,
            (req.url, req.account_id),
        )
        conn.commit()
        job_id = cursor.lastrowid
        return {"job_id": job_id}
    finally:
        conn.close()


@router.get("/jobs", response_model=List[JobResponse])
def list_jobs():
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT j.id, j.url, j.account_id, a.username as account_username, a.username as username,
                   j.status, j.result, j.attempts, j.created_at, j.updated_at
            FROM jobs j
            JOIN accounts a ON j.account_id = a.id
            ORDER BY j.id DESC
            LIMIT 50
            """
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()
