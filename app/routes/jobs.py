import os
import sqlite3
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import JSONResponse
from app.db import get_db_connection
from app.models import JobResponse, LikeMyPostRequest, LikeMyPostResponse, LikeRequest

router = APIRouter(prefix="/api", tags=["jobs"])


@router.post("/like-my-post", response_model=LikeMyPostResponse)
def like_my_post(req: LikeMyPostRequest):
    url = req.url.strip()
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid URL format. Must start with http:// or https://",
        )

    default_max = int(os.getenv("MAX_LIKES_PER_POST", "50"))
    max_likes = req.max_likes if (req.max_likes is not None and req.max_likes > 0) else default_max

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, username FROM accounts WHERE status = 'ok' ORDER BY id ASC")
        accounts = cursor.fetchall()

        if not accounts:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No active accounts available in pool",
            )

        enqueued = 0
        skipped_already_liked = 0
        job_ids: List[int] = []

        for acc in accounts:
            account_id = acc["id"]
            account_username = acc["username"]

            if enqueued >= max_likes:
                break

            cursor.execute(
                "SELECT id FROM jobs WHERE url = ? AND account_id = ?",
                (url, account_id),
            )
            existing = cursor.fetchone()
            if existing:
                skipped_already_liked += 1
            else:
                cursor.execute(
                    """
                    INSERT INTO jobs (url, account_id, account_username, status, attempts)
                    VALUES (?, ?, ?, 'pending', 0)
                    """,
                    (url, account_id, account_username),
                )
                conn.commit()
                job_ids.append(cursor.lastrowid)
                enqueued += 1

        return LikeMyPostResponse(
            url=url,
            enqueued=enqueued,
            skipped_already_liked=skipped_already_liked,
            job_ids=job_ids,
        )
    finally:
        conn.close()


@router.post("/like")
def create_like_job(req: LikeRequest):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, username, status FROM accounts WHERE id = ?", (req.account_id,)
        )
        account = cursor.fetchone()
        if not account or account["status"] != "ok":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Account does not exist or status is not 'ok'",
            )

        cursor.execute(
            """
            SELECT j.id, j.url, j.account_id, j.status, j.result, j.attempts, j.created_at, j.updated_at,
                   COALESCE(a.username, j.account_username, 'Deleted Account') as username
            FROM jobs j
            LEFT JOIN accounts a ON j.account_id = a.id
            WHERE j.url = ? AND j.account_id = ?
            """,
            (req.url, req.account_id),
        )
        existing_job = cursor.fetchone()
        if existing_job:
            job_dict = dict(existing_job)
            job_dict["job_id"] = existing_job["id"]
            job_dict["account_username"] = existing_job["username"]
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={
                    "detail": "Job already exists",
                    "job_id": existing_job["id"],
                    "job": job_dict,
                },
            )

        cursor.execute(
            """
            INSERT INTO jobs (url, account_id, account_username, status, attempts)
            VALUES (?, ?, ?, 'pending', 0)
            """,
            (req.url, req.account_id, account["username"]),
        )
        conn.commit()
        job_id = cursor.lastrowid
        return {"job_id": job_id}
    finally:
        conn.close()


@router.get("/jobs", response_model=List[JobResponse])
def list_jobs(url: Optional[str] = Query(None)):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        if url:
            cursor.execute(
                """
                SELECT j.id, j.url, COALESCE(j.account_id, 0) as account_id,
                       COALESCE(a.username, j.account_username, 'Deleted Account') as account_username,
                       COALESCE(a.username, j.account_username, 'Deleted Account') as username,
                       j.status, j.result, j.attempts, j.created_at, j.updated_at
                FROM jobs j
                LEFT JOIN accounts a ON j.account_id = a.id
                WHERE j.url = ?
                ORDER BY j.id DESC
                LIMIT 50
                """,
                (url.strip(),),
            )
        else:
            cursor.execute(
                """
                SELECT j.id, j.url, COALESCE(j.account_id, 0) as account_id,
                       COALESCE(a.username, j.account_username, 'Deleted Account') as account_username,
                       COALESCE(a.username, j.account_username, 'Deleted Account') as username,
                       j.status, j.result, j.attempts, j.created_at, j.updated_at
                FROM jobs j
                LEFT JOIN accounts a ON j.account_id = a.id
                ORDER BY j.id DESC
                LIMIT 50
                """
            )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()
