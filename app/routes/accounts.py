import sqlite3
from typing import List
from fastapi import APIRouter, HTTPException, status
from app.db import get_db_connection
from app.models import AccountCreate, AccountResponse

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.post("", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
def create_account(account_in: AccountCreate):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO accounts (username, session_json, proxy, status)
            VALUES (?, ?, ?, 'ok')
            """,
            (account_in.username, account_in.session_json, account_in.proxy),
        )
        conn.commit()
        account_id = cursor.lastrowid
        cursor.execute(
            """
            SELECT id, username, proxy, status, last_error, created_at
            FROM accounts WHERE id = ?
            """,
            (account_id,),
        )
        row = cursor.fetchone()
        return dict(row)
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account username already exists",
        )
    finally:
        conn.close()


@router.get("", response_model=List[AccountResponse])
def list_accounts():
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, username, proxy, status, last_error, created_at
            FROM accounts
            ORDER BY id DESC
            """
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


@router.delete("/{account_id}")
def delete_account(account_id: int):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, username FROM accounts WHERE id = ?", (account_id,))
        account = cursor.fetchone()
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Account not found",
            )
        # Preserve historical username and set account_id = NULL on jobs
        cursor.execute(
            """
            UPDATE jobs
            SET account_id = NULL,
                account_username = COALESCE(account_username, ?)
            WHERE account_id = ?
            """,
            (account["username"], account_id),
        )
        cursor.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        conn.commit()
        return {"status": "ok"}
    finally:
        conn.close()
