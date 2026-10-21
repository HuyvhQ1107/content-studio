# Content Studio

**Content Studio** is a self-hosted web app that turns a single topic into ready-to-publish content using a team of AI agents. Type in a topic, and a [CrewAI](https://github.com/crewAIInc/crewAI) crew powered by **Google Gemini** researches the web, writes a blog post, and drafts social media posts for you, all in a chat-style interface.

![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-backend-009688?logo=fastapi)
![CrewAI](https://img.shields.io/badge/CrewAI-multi--agent-orange)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791?logo=postgresql)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker)

---

## ✨ Features

- **Multi-agent content pipeline**: three agents work in sequence:
  1. 🔎 **Senior Research Analyst** searches the web (via Serper) and writes a detailed research report.
  2. ✍️ **Tech Content Strategist** turns the research into an engaging 4-paragraph blog post.
  3. 📣 **Social Media Strategist** *(optional)* summarizes the blog into 2–3 LinkedIn/Twitter posts.
- **Chat-style UI** with conversation history, a sidebar, and suggested topics.
- **Output language**: Vietnamese or English.
- **Live progress**: jobs run in the background and the UI polls for progress (e.g. `2/3` tasks done).
- **Tabbed results** for each agent's output, with a one-click *Copy* button and token usage stats.
- **User accounts**: register and log in with scrypt-hashed passwords and HTTP-only session cookies (30 days).
- **Optional invite code** so only people you invite can register.
- **Persistent history** stored in PostgreSQL (SQLite works for quick local testing).
- **Safe restarts**: jobs that were running when the server stopped are marked as interrupted on startup.
- **Docker-ready**, with separate Compose files for production, development (hot reload), and [Coolify](https://coolify.io/).

---

## 🏗️ Architecture

```mermaid
flowchart LR
    U["Browser (HTML/CSS/JS)"] -- REST + cookie --> API["FastAPI backend"]
    API -- SQLAlchemy --> DB[("PostgreSQL")]
    API -- ThreadPoolExecutor --> C["CrewAI crew"]
    C --> R["Research Agent"] --> W["Writer Agent"] --> S["Social Agent"]
    R -- SerperDevTool --> G["Google Search (Serper)"]
    C -- LLM --> GM["Google Gemini"]
```

The backend serves the static frontend and the JSON API from the same process. When a topic comes in, the API stores a `running` message and hands the crew job to a background thread pool (2 concurrent jobs max). As each task finishes, the worker updates progress in the database, and the frontend polls `/api/messages/{id}` until the job is `done` or `error`.

---

## 📁 Project Structure

```
content_studio/
├── backend/
│   ├── main.py              # FastAPI app: auth, conversations, chat API, static files
│   └── crew_service.py      # CrewAI agents & tasks (Research → Writer → Social)
├── database/
│   └── db.py                # SQLAlchemy engine & models (User, Session, Conversation, Message)
├── frontend/
│   ├── index.html           # Single-page UI
│   ├── app.js               # UI logic, API calls, polling
│   └── style.css            # Styles
├── run.py                   # Entry point (uvicorn)
├── requirements.txt
├── Dockerfile
├── docker-compose.yml           # Production: app + PostgreSQL
├── docker-compose.dev.yml       # Dev override: mounted source + auto-reload
└── docker-compose.coolify.yml   # Deployment on Coolify
```

---

## 🔑 Prerequisites

- A **Google AI (Gemini) API key**: <https://aistudio.google.com/apikey>
- A **Serper API key** (Google Search API): <https://serper.dev>
- **Docker** + Docker Compose, **or** Python 3.11+ (plus PostgreSQL if you don't use SQLite)

---

## ⚙️ Configuration

Create a `.env` file in the project root:

```env
# ----- Required API keys -----
GOOGLE_API_KEY=your_gemini_api_key
SERPER_API_KEY=your_serper_api_key

# ----- Docker (docker compose up) -----
# Use only letters and numbers. Only applied the first time the database is initialized.
POSTGRES_USER=content
POSTGRES_PASSWORD=change_me
POSTGRES_DB=content_studio

# ----- Running without Docker (python run.py) -----
# Local PostgreSQL:
# DATABASE_URL=postgresql://user:password@localhost:5432/content_studio
# Or SQLite for quick testing:
# DATABASE_URL=sqlite:///content_studio.db

# ----- Optional -----
# INVITE_CODE=my-secret-code             # require this code to register
# GEMINI_MODEL=gemini/gemini-3.1-flash-lite
# COOKIE_SECURE=true                     # enable when served over HTTPS
```

| Variable | Required | Default | Description |
|---|---|---|---|
| `GOOGLE_API_KEY` | ✅ | – | Google Gemini API key |
| `SERPER_API_KEY` | ✅ | – | Serper.dev key used by the web search tool |
| `DATABASE_URL` | ✅ (non-Docker) | – | `postgresql://...` or `sqlite:///...` (set automatically by Docker Compose) |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | ✅ (Docker) | – | Credentials for the PostgreSQL container |
| `INVITE_CODE` | ❌ | empty | If set, new users must enter this code to register |
| `GEMINI_MODEL` | ❌ | `gemini/gemini-3.1-flash-lite` | Any Gemini model supported by CrewAI/LiteLLM |
| `COOKIE_SECURE` | ❌ | `false` | Mark the session cookie as `Secure` (use behind HTTPS) |
| `HOST` / `PORT` | ❌ | `127.0.0.1` / `8000` | Server bind address |

> ⚠️ Never commit your `.env` file. It is already listed in `.gitignore`.

---

## 🚀 Getting Started

### Option 1: Docker (recommended)

```bash
git clone https://github.com/HuyvhQ1107/content-studio.git
cd content-studio
# create .env as described above
docker compose up -d --build
```

Open <http://localhost:8000>, create an account, log in, and send your first topic.

**Development mode** (source code is mounted and the server reloads on changes):

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

### Option 2: Run locally with Python

```bash
git clone https://github.com/HuyvhQ1107/content-studio.git
cd content-studio

python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
# create .env and set DATABASE_URL (PostgreSQL or SQLite)
python run.py
```

Then open <http://127.0.0.1:8000>. Database tables are created automatically on first start.

### Option 3: Deploy on Coolify

1. Create a new **Docker Compose** resource pointing to this repository.
2. Select `docker-compose.coolify.yml` as the compose file.
3. In **Environment Variables**, set `POSTGRES_USER`, `POSTGRES_PASSWORD`, `GOOGLE_API_KEY`, `SERPER_API_KEY` (and optionally `POSTGRES_DB`, `INVITE_CODE`, `GEMINI_MODEL`).
4. Assign your domain to the `app` service on port `8000`. `COOKIE_SECURE` defaults to `true`.

---

## 🔌 API Reference

All endpoints except auth require a valid session cookie (`cs_session`).

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/auth/me` | Current user and whether an invite code is required |
| `POST` | `/api/auth/register` | Register `{ username, password, invite_code? }` |
| `POST` | `/api/auth/login` | Log in and set the session cookie |
| `POST` | `/api/auth/logout` | Log out and delete the session |
| `GET` | `/api/conversations` | List the user's conversations |
| `GET` | `/api/conversations/{id}` | Get all messages in a conversation |
| `DELETE` | `/api/conversations/{id}` | Delete a conversation |
| `POST` | `/api/chat` | Submit a topic `{ conversation_id?, topic, language, with_social }` |
| `GET` | `/api/messages/{id}` | Poll a message's status / progress / result |

Interactive API docs are available at `/docs` (Swagger UI).

**Rules:**
- Username: 3–30 characters (`A-Z a-z 0-9 _ . -`). Password: 8–128 characters.
- Topic: 3–300 characters.
- Each user can run only **one** job at a time.

---

## 🗄️ Data Model

```mermaid
erDiagram
    users ||--o{ sessions : has
    users ||--o{ conversations : owns
    conversations ||--o{ messages : contains
    users { int id string username string password_hash datetime created_at }
    sessions { string token int user_id datetime expires_at }
    conversations { int id int user_id string title datetime updated_at }
    messages { int id int conversation_id string role text text string status int done int total json result text error }
```

---

## 🛠️ Tech Stack

- **Backend:** FastAPI, Uvicorn, SQLAlchemy 2.0, psycopg 3
- **AI:** CrewAI, crewai-tools (`SerperDevTool`), Google Gemini
- **Database:** PostgreSQL 16 (SQLite supported for local testing)
- **Frontend:** Vanilla HTML / CSS / JavaScript (no build step)
- **Deployment:** Docker, Docker Compose, Coolify

---

## 🤝 Contributing

Contributions, issues, and feature requests are welcome! Feel free to open an issue or submit a pull request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m "Add amazing feature"`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request
