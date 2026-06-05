# Deploying KishanX Trading Signals to Vercel & Render

> **Note:** This project is a Python Flask application with WebSocket support (SocketIO), background threads, and a SQLite database. It is **not natively suited for serverless platforms** like Vercel. Render (Web Services) is the recommended choice.

---

## Option 1: Deploy to Render (Recommended)

### Prerequisites

- A [Render](https://render.com) account
- Your project pushed to a GitHub/GitLab repository

### Steps

1. **Push your code to GitHub** (Render will pull from there).

2. **Create a new Web Service** on Render:
   - Click **New +** > **Web Service**
   - Connect your GitHub repo
   - Fill in:
     - **Name:** `kishanx-trading`
     - **Region:** Choose closest to your users
     - **Branch:** `main`
     - **Runtime:** `Python 3`
     - **Build Command:** `pip install -r requirements.txt`
     - **Start Command:** `gunicorn -k eventlet -w 1 wsgi:application --bind 0.0.0.0:$PORT`
     - **Plan:** Free or Starter ($7/mo) — Free works but spins down after inactivity

3. **Set Environment Variables** (copy from your `.env`):
   - `SECRET_KEY` — generate a strong random key
   - `FLASK_ENV` = `production`
   - `ENV` = `production`
   - `PORT` — Render injects this automatically
   - All API keys (GEMINI_API_KEY, DHAN_API_TOKEN, ALPHA_VANTAGE_API_KEY, etc.)
   - Set `MYSQL_HOST` to a cloud DB or remove if using SQLite

4. **Deploy** — Render auto-deploys on push.

### Important Notes for Render

- **SQLite persistence:** Render's free tier has an ephemeral filesystem. The SQLite DB (`kishanx.db`) will reset on every deploy/restart. For persistent data, either:
  - Upgrade to Render's **Starter** plan ($7/mo) which offers persistent disk
  - Switch to a cloud MySQL/PostgreSQL (Render provides managed PostgreSQL)
- **WebSocket support:** The start command above uses `eventlet` for SocketIO compatibility.
- **Cron/background tasks:** The trading bot and auto-trader threads run inside the app process. On Render, use a separate **Cron Job** or **Background Worker** if you need reliable scheduling.

---

## Option 2: Deploy to Vercel (Limited / Experimental)

> **Vercel** is designed for serverless functions. A long-running Flask app with WebSockets and background threads **will not work properly** on Vercel's free tier. Use only if you understand these limitations.

### What Works

- Static files and basic API routes (HTTP requests)
- Serverless functions under 10s execution timeout

### What Does NOT Work

- WebSocket connections (SocketIO)
- Background threads (auto-trader, price monitors)
- SQLite file persistence (read-only filesystem)
- Long-running processes

### Required Changes (if proceeding anyway)

1. **Create `vercel.json`** in project root:
   ```json
   {
     "builds": [
       {
         "src": "wsgi.py",
         "use": "@vercel/python"
       }
     ],
     "routes": [
       {
         "src": "/(.*)",
         "dest": "wsgi.py"
       }
     ]
   }
   ```

2. **Add a `runtime.txt`** (optional, Vercel auto-detects Python):
   ```
   python-3.9
   ```

3. **Remove or disable SocketIO** — Vercel doesn't support persistent WebSocket connections.

4. **Use an external database** — SQLite won't persist. Switch to Render PostgreSQL, AWS RDS, or MongoDB Atlas.

5. **Disable background threads** — Remove auto-trader, monitor, and scheduler threads.

6. **Push and deploy** via Vercel dashboard (import GitHub repo).

### Vercel Recommendation

For this project, **do not use Vercel** unless you strip it down to a read-only API. Use Render instead.

---

## Comparison Summary

| Feature                  | Render (Web Service)     | Vercel (Serverless)       |
|--------------------------|--------------------------|---------------------------|
| Python Flask             | Full support             | Limited (timeout 10s)     |
| WebSocket / SocketIO     | Yes (with eventlet)      | Not supported             |
| Background threads       | Yes                      | Not supported             |
| SQLite persistence       | With persistent disk     | Not supported             |
| Free tier                | Spins down on inactivity | Better for APIs           |
| Ease of setup            | Medium                   | Easy (for simple apps)    |
| **Verdict**              | **Recommended**          | **Not recommended**       |

---

## Quick Start — Deploy to Render (One-Click)

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy)

1. Click the button above
2. Connect your GitHub repo
3. Set environment variables (use `.env` as reference)
4. Deploy
