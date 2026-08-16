# Post Like Bot

Post Like Bot is a self-hosted, single-user web application designed to deliver automated likes to your social media posts using a pool of authenticated secondary accounts.

## What It Does
- **Account Pool Management**: Save and manage authenticated pool accounts (with optional proxy settings). Each pool account represents a secondary account used to deliver likes.
- **Like My Post**: Paste a URL of your own social media post, set an optional max likes cap, and the app enqueues one like job per available pool account.
- **Background Worker**: Asynchronously executes like jobs across pool accounts using platform APIs (`instagrapi` for Instagram) with per-account pacing and deduplication.
- **Live Status & Filtering**: Monitor live job execution and filter jobs by post URL in a dark-mode web UI.

---

## Setup Instructions

### Local Development Setup

1. **Clone the repository and enter directory**:
   ```bash
   cd post-like-bot
   ```

2. **Create and activate a virtual environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Set environment variables (optional)**:
   Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
   Key environment options:
   - `MAX_LIKES_PER_POST`: Default cap for likes enqueued per post (default `50`).
   - `MIN_DELAY` / `MAX_DELAY`: Delay in seconds between consecutive likes from the same account (defaults `30` and `90`).

5. **Run the FastAPI application with Uvicorn**:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
   Open `http://localhost:8000` in your browser.

---

### Docker / Docker Compose Setup

Run using Docker Compose:
```bash
docker compose up --build
```
The application will be accessible at `http://localhost:8000`.

---

## How to Export Your Session for Instagram

To export session JSON for each pool account using `instagrapi`:

1. Open Python in your environment:
   ```python
   import json
   from instagrapi import Client

   cl = Client()
   cl.login("POOL_ACCOUNT_USERNAME", "POOL_ACCOUNT_PASSWORD")

   # Export settings dict containing authenticated cookies and session tokens
   settings = cl.get_settings()
   print(json.dumps(settings))
   ```
2. Copy the printed JSON string output.

---

## How to Add Pool Accounts in the UI

1. Open the web interface at `http://localhost:8000`.
2. Under **Pool Accounts**:
   - Enter the secondary account **Username**.
   - Paste the exported **Session JSON** into the textarea.
   - (Optional) Enter a **Proxy** URL for that account (e.g., `http://user:pass@proxy.example.com:8080`).
3. Click **Add Account**.
4. Repeat for as many secondary pool accounts as you have.

> **Note**: Each pool account requires its own distinct session JSON. The intended usage is adding secondary/alt accounts into the pool so they can deliver likes to your main post.

---

## How to Use "Like My Post"

1. In the **Like My Post (Pool)** section:
   - Paste the URL of your post (e.g., `https://www.instagram.com/p/...`).
   - Set **Max Likes (Cap)** (prefilled with `MAX_LIKES_PER_POST` default, e.g. `50`).
2. Click **Send Likes**.
3. The app will enqueue 1 pending like job per available `ok` pool account up to your max likes cap.
4. Accounts that have already liked that post URL will automatically be skipped to avoid duplicate liking.
5. In the **Live Jobs** table, you can see real-time progress or filter jobs by post URL.

---

## Worker Pacing and Exception Handling

- **Pacing**: After an account completes a like job, the background worker waits a random delay between `MIN_DELAY` (default 30 seconds) and `MAX_DELAY` (default 90 seconds) before executing the next like from that same account. Jobs for different accounts in the pool run concurrently.
- **Action Block Handling**: If a pool account encounters an action block exception (`ChallengeRequired`, `FeedbackRequired`, `LoginRequired`, `ClientThrottledError`, etc.), its status is updated to `action_blocked` and no further jobs are assigned to it.
- **Retries**: For transient network errors, jobs retry up to `MAX_ATTEMPTS` (default 2) before being marked as `failed`.

---

## Disclaimer

> **WARNING**: Automated interaction and automated post liking violate the Terms of Service of most social media platforms (including Instagram). Using automated tools may result in temporary action blocks, session invalidation, or permanent account bans. Use this software strictly at your own risk.
