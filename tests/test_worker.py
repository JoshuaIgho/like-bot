import asyncio
import json
import os
import pytest
from app.db import init_db, get_db_connection
from app.engine.base import LikeEngine
from app.worker import process_pending_jobs, ACCOUNT_NEXT_ALLOWED_TIME, RUNNING_ACCOUNTS


@pytest.fixture(autouse=True)
def setup_worker_test_env(tmp_path):
    db_file = tmp_path / "test_worker.db"
    os.environ["DB_PATH"] = str(db_file)
    os.environ["MIN_DELAY"] = "0"
    os.environ["MAX_DELAY"] = "0"
    os.environ["MAX_ATTEMPTS"] = "2"
    ACCOUNT_NEXT_ALLOWED_TIME.clear()
    RUNNING_ACCOUNTS.clear()
    init_db(str(db_file))
    yield
    if db_file.exists():
        try:
            os.remove(db_file)
        except OSError:
            pass


class SuccessEngine(LikeEngine):
    def load_session(self, session_json: str, proxy: str | None = None) -> None:
        pass

    def extract_media_id(self, url: str) -> str:
        return "media_12345"

    def like(self, media_id: str) -> bool:
        return True


class BlockException(Exception):
    pass


# Give class the name ChallengeRequired so is_block_exception identifies it
BlockException.__name__ = "ChallengeRequired"


class BlockEngine(LikeEngine):
    def load_session(self, session_json: str, proxy: str | None = None) -> None:
        pass

    def extract_media_id(self, url: str) -> str:
        return "media_12345"

    def like(self, media_id: str) -> bool:
        raise BlockException("Action block required")


class RetryEngine(LikeEngine):
    calls = 0

    def load_session(self, session_json: str, proxy: str | None = None) -> None:
        pass

    def extract_media_id(self, url: str) -> str:
        return "media_12345"

    def like(self, media_id: str) -> bool:
        RetryEngine.calls += 1
        if RetryEngine.calls == 1:
            raise Exception("Temporary connection reset")
        return True


def test_worker_lifecycle():
    async def _test():
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO accounts (username, session_json, status) VALUES ('user1', ?, 'ok')",
            (json.dumps({"session": "123"}),),
        )
        acc_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO jobs (url, account_id, status) VALUES ('https://instagr.am/p/ABC', ?, 'pending')",
            (acc_id,),
        )
        job_id = cursor.lastrowid
        conn.commit()
        conn.close()

        await process_pending_jobs(engine_factory=lambda: SuccessEngine())

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT status, result FROM jobs WHERE id = ?", (job_id,))
        job = cursor.fetchone()
        conn.close()

        assert job["status"] == "done"
        assert "liked media_12345" in job["result"]

    asyncio.run(_test())


def test_worker_block():
    async def _test():
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO accounts (username, session_json, status) VALUES ('user2', ?, 'ok')",
            (json.dumps({"session": "123"}),),
        )
        acc_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO jobs (url, account_id, status) VALUES ('https://instagr.am/p/DEF', ?, 'pending')",
            (acc_id,),
        )
        job_id = cursor.lastrowid
        conn.commit()
        conn.close()

        await process_pending_jobs(engine_factory=lambda: BlockEngine())

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT status, last_error FROM accounts WHERE id = ?", (acc_id,))
        account = cursor.fetchone()

        cursor.execute("SELECT status, result FROM jobs WHERE id = ?", (job_id,))
        job = cursor.fetchone()
        conn.close()

        assert account["status"] == "action_blocked"
        assert "Action block required" in account["last_error"]
        assert job["status"] == "blocked"
        assert "Action block required" in job["result"]

    asyncio.run(_test())


def test_worker_retry():
    async def _test():
        RetryEngine.calls = 0

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO accounts (username, session_json, status) VALUES ('user3', ?, 'ok')",
            (json.dumps({"session": "123"}),),
        )
        acc_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO jobs (url, account_id, status, attempts) VALUES ('https://instagr.am/p/GHI', ?, 'pending', 0)",
            (acc_id,),
        )
        job_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Attempt 1: Fails with generic exception
        await process_pending_jobs(engine_factory=lambda: RetryEngine())

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT status, attempts FROM jobs WHERE id = ?", (job_id,))
        job_attempt1 = cursor.fetchone()
        conn.close()

        assert job_attempt1["status"] == "pending"
        assert job_attempt1["attempts"] == 1

        # Clear pacing tracking for retry call
        ACCOUNT_NEXT_ALLOWED_TIME.clear()
        RUNNING_ACCOUNTS.clear()

        # Attempt 2: Succeeds
        await process_pending_jobs(engine_factory=lambda: RetryEngine())

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT status, attempts, result FROM jobs WHERE id = ?", (job_id,))
        job_attempt2 = cursor.fetchone()
        conn.close()

        assert job_attempt2["status"] == "done"
        assert job_attempt2["attempts"] == 1
        assert "liked media_12345" in job_attempt2["result"]

    asyncio.run(_test())
