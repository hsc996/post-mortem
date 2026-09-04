# PostMortem

An incident and shift handover monitoring/reporting app for high-consequence environments, providing incident tracking, temporary mitigation management, and shift handovers, backed by full audit logging and role-based access control.

## Features

- Incident lifecycle management (create, update, resolve) with state tracking
- Temporary mitigation tracking so fixes in progress aren't forgotten across shifts
- Shift handover support backed by a per-incident audit trail
- JWT-based authentication with role-based access control and token revocation
- Rate limiting and configurable CORS

## Tech Stack

- **Language/Runtime:** Python 3.12
- **Framework:** FastAPI + Uvicorn
- **Database:** PostgreSQL, accessed via SQLAlchemy (async) and asyncpg
- **Migrations:** Alembic
- **Auth:** PyJWT, bcrypt
- **Rate limiting:** SlowAPI
- **Validation/config:** Pydantic v2 / pydantic-settings
- **Testing:** pytest, pytest-asyncio, httpx, aiosqlite
- **Linting:** Ruff
- **Containerization:** Docker / Docker Compose

## Installation

### Prerequisites

- Python 3.12+
- Docker & Docker Compose (recommended, no local PostgreSQL install needed), or a local PostgreSQL instance if running without Docker

### 1. Clone the repository

```bash
git clone <repository-url>
cd post-mortem
```

### 2. Configure environment variables

Copy the example env file and fill in your own values:

```bash
cp .env.example .env
```

Required variables:

| Variable | Description |
|---|---|
| `DATABASE_URL` | Async Postgres connection string, e.g. `postgresql+asyncpg://user:password@localhost:5432/postmortem` |
| `SECRET_KEY` | Secret used to sign JWTs (min. 32 characters, no placeholder values) |
| `ALGORITHM` | JWT signing algorithm (defaults to `HS256`) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access token lifetime in minutes (defaults to 1440) |
| `CORS_ORIGINS` | Comma-separated list of allowed CORS origins |

### 3. Run with Docker Compose (recommended)

```bash
docker compose up --build
```

This starts a Postgres container, runs Alembic migrations, and launches the API at `http://localhost:8000`.

### 4. Run locally without Docker

Install dependencies (including dev/test extras):

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Apply database migrations:

```bash
alembic upgrade head
```

Start the API:

```bash
uvicorn src.main:app --reload
```

The API will be available at `http://localhost:8000`, with interactive docs at `http://localhost:8000/docs`.

### 5. Run tests

```bash
pytest
```

## Health Check

```
GET /healthz
```
