# Post Like Bot

Post Like Bot is a self-hosted, single-user web application designed to automatically like social media posts using authenticated sessions.

## What It Does
- **Account Management**: Save and manage authenticated account sessions (with optional proxy settings).
- **Post Liking**: Submit post URLs to be liked by your saved accounts.
- **Background Worker**: Asynchronously processes pending jobs in the background through platform APIs (`instagrapi` for Instagram).
- **Live Status UI**: Monitor account statuses and real-time job execution logs in a dark-mode web dashboard.

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
   Copy `.env.example` to `.env` or export environment variables:
   ```bash
   cp .env.example .env
   ```

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

To export your session JSON using `instagrapi`:

1. Open Python in your environment:
   ```python
   import json
   from instagrapi import Client

   cl = Client()
   cl.login("YOUR_INSTAGRAM_USERNAME", "YOUR_INSTAGRAM_PASSWORD")

   # Export settings dict containing authenticated cookies and session tokens
   settings = cl.get_settings()
   print(json.dumps(settings))
   ```
2. Copy the printed JSON string output.

---

## How to Add an Account in the UI

1. Open the web interface at `http://localhost:8000`.
2. Under the **Accounts** section:
   - Enter your account **Username**.
   - Paste the exported **Session JSON** into the textarea.
   - (Optional) Enter a **Proxy** URL (e.g., `http://user:pass@proxy.example.com:8080`).
3. Click **Add Account**.
4. The account will appear in the table with an `ok` status badge and become available in the post-liking dropdown.

---

## Worker Pacing and Exception Handling

- **Pacing**: After an account completes a like job, the background worker waits a random delay between `MIN_DELAY` (default 30 seconds) and `MAX_DELAY` (default 90 seconds) before executing the next like from that same account. No two likes from the same account occur closer than `MIN_DELAY` apart.
- **Action Block Handling**: If the platform raises an action block exception (`ChallengeRequired`, `FeedbackRequired`, `LoginRequired`, `ClientThrottledError`, etc.), the account status is updated to `action_blocked` and further jobs for that account are suspended.
- **Retries**: For transient errors (e.g. temporary network timeouts), the job increments its attempt counter and retries up to `MAX_ATTEMPTS` (default 2) before marking the job as `failed`.

---

## Disclaimer

> **WARNING**: Automated interaction and automated post liking violate the Terms of Service of most social media platforms (including Instagram). Using automated tools may result in temporary action blocks, session invalidation, or permanent account bans. Use this software strictly at your own risk.
