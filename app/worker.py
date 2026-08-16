import asyncio
import logging
import os
import random
import time
from typing import Callable, Dict, Optional

from app.db import get_db_connection
from app.engine.base import LikeEngine
from app.engine.instagrapi_engine import InstagrapiEngine

logger = logging.getLogger("worker")
logging.basicConfig(level=logging.INFO)

BLOCK_NAMES = {
    "ChallengeRequired",
    "FeedbackRequired",
    "ReloginChallenge",
    "LoginRequired",
    "ClientThrottledError",
    "ClientLoginRequired",
    "ReloginAttemptExceeded",
}

# Tracking next allowed timestamp per account for pacing
ACCOUNT_NEXT_ALLOWED_TIME: Dict[int, float] = {}
# Tracking currently running accounts to avoid concurrent execution per account
RUNNING_ACCOUNTS = set()


def is_block_exception(e: Exception) -> bool:
    for cls in e.__class__.__mro__:
        if cls.__name__ in BLOCK_NAMES:
            return True
    return False


def get_default_engine() -> LikeEngine:
    return InstagrapiEngine()


ENGINE_FACTORY: Callable[[], LikeEngine] = get_default_engine


def redact_sensitive(text: str) -> str:
    if not text:
        return text
    # Basic redaction helper to ensure raw session JSON/cookies aren't leaked in messages
    return text.replace("session_json", "[REDACTED]")


def run_job_sync(job_id: int, url: str, account_id: int, session_json: str, proxy: Optional[str], engine_factory: Callable[[], LikeEngine]):
    conn = get_db_connection()
    try:
        engine = engine_factory()
        engine.load_session(session_json, proxy)
        media_id = engine.extract_media_id(url)
        success = engine.like(media_id)

        cursor = conn.cursor()
        if success or success is None or success is True:
            result_str = f"liked {media_id}"
            cursor.execute(
                """
                UPDATE jobs
                SET status = 'done', result = ?, updated_at = datetime('now')
                WHERE id = ?
                """,
                (result_str, job_id),
            )
            conn.commit()
    except Exception as e:
        err_msg = redact_sensitive(str(e))
        cursor = conn.cursor()
        if is_block_exception(e):
            # Block exception: set account status = 'action_blocked', job status = 'blocked'
            cursor.execute(
                """
                UPDATE accounts
                SET status = 'action_blocked', last_error = ?
                WHERE id = ?
                """,
                (err_msg, account_id),
            )
            cursor.execute(
                """
                UPDATE jobs
                SET status = 'blocked', result = ?, updated_at = datetime('now')
                WHERE id = ?
                """,
                (err_msg, job_id),
            )
            conn.commit()
        else:
            # Other exception: retry logic
            cursor.execute("SELECT attempts FROM jobs WHERE id = ?", (job_id,))
            row = cursor.fetchone()
            current_attempts = row["attempts"] if row else 0
            new_attempts = current_attempts + 1
            max_attempts = int(os.getenv("MAX_ATTEMPTS", "2"))

            if new_attempts >= max_attempts:
                cursor.execute(
                    """
                    UPDATE jobs
                    SET status = 'failed', attempts = ?, result = ?, updated_at = datetime('now')
                    WHERE id = ?
                    """,
                    (new_attempts, err_msg, job_id),
                )
            else:
                cursor.execute(
                    """
                    UPDATE jobs
                    SET status = 'pending', attempts = ?, result = ?, updated_at = datetime('now')
                    WHERE id = ?
                    """,
                    (new_attempts, err_msg, job_id),
                )
            conn.commit()
    finally:
        conn.close()


async def execute_job(job: dict, engine_factory: Callable[[], LikeEngine]):
    account_id = job["account_id"]
    job_id = job["id"]
    try:
        await asyncio.to_thread(
            run_job_sync,
            job_id,
            job["url"],
            account_id,
            job["session_json"],
            job["proxy"],
            engine_factory,
        )
    finally:
        min_delay = float(os.getenv("MIN_DELAY", "30"))
        max_delay = float(os.getenv("MAX_DELAY", "90"))
        if max_delay < min_delay:
            max_delay = min_delay

        delay = random.uniform(min_delay, max_delay) if max_delay > 0 else 0
        ACCOUNT_NEXT_ALLOWED_TIME[account_id] = time.time() + delay
        RUNNING_ACCOUNTS.discard(account_id)


async def process_pending_jobs(engine_factory: Optional[Callable[[], LikeEngine]] = None):
    if engine_factory is None:
        engine_factory = ENGINE_FACTORY

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Find accounts that are 'ok'
        cursor.execute("SELECT id FROM accounts WHERE status = 'ok'")
        accounts = cursor.fetchall()

        now = time.time()
        tasks = []

        for acc in accounts:
            account_id = acc["id"]
            if account_id in RUNNING_ACCOUNTS:
                continue
            if now < ACCOUNT_NEXT_ALLOWED_TIME.get(account_id, 0):
                continue

            # Fetch oldest pending job for this account
            cursor.execute(
                """
                SELECT j.id, j.url, j.account_id, a.session_json, a.proxy
                FROM jobs j
                JOIN accounts a ON j.account_id = a.id
                WHERE j.account_id = ? AND j.status = 'pending' AND a.status = 'ok'
                ORDER BY j.created_at ASC, j.id ASC
                LIMIT 1
                """,
                (account_id,),
            )
            job_row = cursor.fetchone()
            if not job_row:
                continue

            job = dict(job_row)
            job_id = job["id"]

            # Claim job atomically
            cursor.execute(
                """
                UPDATE jobs
                SET status = 'running', updated_at = datetime('now')
                WHERE id = ? AND status = 'pending'
                """,
                (job_id,),
            )
            conn.commit()

            if cursor.rowcount > 0:
                RUNNING_ACCOUNTS.add(account_id)
                task = asyncio.create_task(execute_job(job, engine_factory))
                tasks.append(task)

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        conn.close()


async def run_worker():
    while True:
        try:
            await process_pending_jobs()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Worker loop error: {e}")
        await asyncio.sleep(1)
