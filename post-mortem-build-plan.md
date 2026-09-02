# PulseGuard — Engineering Build Plan & System Specification

## 1. System Overview & Core Objectives
PulseGuard is an operational incident tracking and shift-handover platform designed for high-consequence environments. It replaces unstructured handovers with auditable timelines, stateful temporary mitigations, and deterministic shift snapshots.

### Key Architectural Principles
* **Stateful Mitigations as First-Class Entities:** Temporary system changes (e.g., manual overrides) have explicit lifecycles, intents, unwind conditions, and TTLs.
* **Read-Time Truth:** Mitigation TTL expiration (`is_expired`) is dynamically calculated at query time. Background workers handle proactive alerts/escalations but are **never** the single source of truth for current state.
* **Optimistic Locking:** All state mutations enforce optimistic concurrency control via a `version` column to prevent silent write clobbering.
* **Immutable Audit Trail:** All mutations automatically create append-only audit entries within the primary database transaction.

---

## 2. Technical Stack

| Layer | Technology | Purpose |
|---|---|---|
| **Language & Runtime** | Python 3.12+ | High-throughput async/await ecosystem |
| **API Framework** | FastAPI | Async REST API, OpenAPI generation, Pydantic v2 validation |
| **ORM & Database Driver** | SQLAlchemy 2.0 (Async) + `asyncpg` | Strict typing, explicit unit-of-work transactions, connection pooling |
| **Database** | PostgreSQL 16+ | Relational data, JSONB audit payloads, row locking |
| **Auth** | OAuth2 + JWT (`pyjwt`, `passlib`) | Lightweight user context for mutation attribution |
| **Testing** | Pytest + `httpx` + `pytest-asyncio` | Unit & integration tests for state transitions and concurrency |
| **Task Queue & Broker** | ARQ + Redis | Async background worker for proactive TTL alerts |
| **Containerization** | Docker + Docker Compose | Multi-stage production container builds |
| **Orchestration** | Kubernetes (k3s / Minikube) | Production-ready manifest configuration |

---

## 3. System Architecture & Component Flow