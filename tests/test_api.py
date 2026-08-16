import json
import os
import pytest
from fastapi.testclient import TestClient
from app.db import init_db, get_db_connection
from app.main import app


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path):
    db_file = tmp_path / "test_api.db"
    os.environ["DB_PATH"] = str(db_file)
    init_db(str(db_file))
    yield
    if db_file.exists():
        try:
            os.remove(db_file)
        except OSError:
            pass


def test_health():
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_accounts_crud():
    client = TestClient(app)

    # Invalid session_json
    bad_payload = {
        "username": "user1",
        "session_json": "invalid-json",
        "proxy": None,
    }
    res = client.post("/api/accounts", json=bad_payload)
    assert res.status_code == 422

    # Valid creation
    valid_payload = {
        "username": "user1",
        "session_json": json.dumps({"sessionid": "abc"}),
        "proxy": "http://proxy:8080",
    }
    res = client.post("/api/accounts", json=valid_payload)
    assert res.status_code == 201
    data = res.json()
    assert data["username"] == "user1"
    assert "session_json" not in data
    assert data["status"] == "ok"
    acc_id = data["id"]

    # Duplicate username
    res_dup = client.post("/api/accounts", json=valid_payload)
    assert res_dup.status_code == 400

    # List accounts
    res_list = client.get("/api/accounts")
    assert res_list.status_code == 200
    accounts = res_list.json()
    assert len(accounts) == 1
    assert "session_json" not in accounts[0]

    # Delete account
    res_del = client.delete(f"/api/accounts/{acc_id}")
    assert res_del.status_code == 200

    # List accounts after delete
    res_list_after = client.get("/api/accounts")
    assert len(res_list_after.json()) == 0


def test_pool_like():
    client = TestClient(app)

    # Create 3 ok accounts
    for i in range(1, 4):
        client.post(
            "/api/accounts",
            json={
                "username": f"pool_user_{i}",
                "session_json": json.dumps({"sessionid": f"sess_{i}"}),
            },
        )

    url = "https://www.instagram.com/p/MY_POST_123/"
    res = client.post(
        "/api/like-my-post",
        json={"url": url, "max_likes": 2},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["enqueued"] == 2
    assert data["skipped_already_liked"] == 0
    assert len(data["job_ids"]) == 2

    # Verify 2 jobs in DB
    jobs_res = client.get(f"/api/jobs?url={url}")
    assert jobs_res.status_code == 200
    jobs = jobs_res.json()
    assert len(jobs) == 2


def test_pool_like_dedupe():
    client = TestClient(app)

    # Create 2 ok accounts
    for i in range(1, 3):
        client.post(
            "/api/accounts",
            json={
                "username": f"dedupe_pool_{i}",
                "session_json": json.dumps({"sessionid": f"sess_{i}"}),
            },
        )

    url = "https://www.instagram.com/p/DEDUPE_POST/"

    # First call: enqueues 2 jobs
    res1 = client.post("/api/like-my-post", json={"url": url})
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["enqueued"] == 2
    assert data1["skipped_already_liked"] == 0

    # Second call for same URL: skips both accounts
    res2 = client.post("/api/like-my-post", json={"url": url})
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["enqueued"] == 0
    assert data2["skipped_already_liked"] == 2
    assert len(data2["job_ids"]) == 0


def test_pool_like_no_accounts():
    client = TestClient(app)
    res = client.post(
        "/api/like-my-post",
        json={"url": "https://www.instagram.com/p/NO_ACCOUNTS/"},
    )
    assert res.status_code == 400
    assert "No active accounts" in res.json()["detail"]


def test_dedupe():
    client = TestClient(app)

    # Create an account
    acc_payload = {
        "username": "dedupe_user",
        "session_json": json.dumps({"sessionid": "xyz"}),
    }
    acc_res = client.post("/api/accounts", json=acc_payload)
    assert acc_res.status_code == 201
    account_id = acc_res.json()["id"]

    like_payload = {
        "url": "https://www.instagram.com/p/CUbK348gsR4/",
        "account_id": account_id,
    }

    # First POST /api/like succeeds
    res1 = client.post("/api/like", json=like_payload)
    assert res1.status_code == 200
    assert "job_id" in res1.json()

    # Second POST /api/like with same URL + account_id returns 409
    res2 = client.post("/api/like", json=like_payload)
    assert res2.status_code == 409
    data2 = res2.json()
    assert "job_id" in data2


def test_like_account_validation():
    client = TestClient(app)

    # Non-existent account
    res = client.post(
        "/api/like",
        json={"url": "https://instagram.com/p/test", "account_id": 9999},
    )
    assert res.status_code == 400

    # Account not ok
    acc_payload = {
        "username": "blocked_user",
        "session_json": json.dumps({"sessionid": "xyz"}),
    }
    acc_res = client.post("/api/accounts", json=acc_payload)
    account_id = acc_res.json()["id"]

    # Mark account action_blocked directly in DB
    conn = get_db_connection()
    conn.execute(
        "UPDATE accounts SET status = 'action_blocked' WHERE id = ?",
        (account_id,),
    )
    conn.commit()
    conn.close()

    res_blocked = client.post(
        "/api/like",
        json={"url": "https://instagram.com/p/test", "account_id": account_id},
    )
    assert res_blocked.status_code == 400
