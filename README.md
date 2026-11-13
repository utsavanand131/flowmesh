# FlowMesh

**A Reliable Event-Driven Microservices Platform**

FlowMesh is a backend-focused microservices project built with Python, FastAPI, gRPC, PostgreSQL, and Redis. It demonstrates service-to-service communication, asynchronous event processing, and reliable distributed-system patterns.

The project focuses on building a resilient backend with reliable event delivery, idempotent processing, retry handling, dead-letter queues, graceful worker shutdown, structured logging, and operational metrics.

## Key Features

- **Microservices Architecture:** Separate Order, Inventory, and Delivery services.
- **API Gateway:** Centralized API access through FastAPI.
- **gRPC Communication:** Efficient service-to-service communication using Protocol Buffers.
- **Event-Driven Processing:** Asynchronous event processing using Redis Streams and consumer groups.
- **PostgreSQL Persistence:** Relational data storage using SQLAlchemy and PostgreSQL.
- **Transactional Outbox Pattern:** Persist events alongside business transactions before publishing them.
- **Idempotent Consumers:** Prevent duplicate event processing.
- **Retry Mechanism:** Retry failed event processing.
- **Dead Letter Queue:** Isolate messages that exceed the maximum delivery attempts.
- **Pending Message Recovery:** Recover messages that remain unacknowledged.
- **Graceful Shutdown:** Allow workers to finish in-flight processing before stopping.
- **Structured Logging:** JSON-formatted application and worker logs.
- **Worker Metrics:** Redis-backed counters exposed through an admin-protected API endpoint.

## Technology Stack

| Category            | Technologies                      |
| ------------------- | --------------------------------- |
| Language            | Python                            |
| API Framework       | FastAPI                           |
| RPC Communication   | gRPC, Protocol Buffers            |
| Database            | PostgreSQL                        |
| ORM                 | SQLAlchemy                        |
| Database Migrations | Alembic                           |
| Message Streaming   | Redis Streams                     |
| Containerization    | Docker, Docker Compose            |
| Testing             | Pytest                            |
| Frontend (planned)  | Next.js, TypeScript, Tailwind CSS |

## Architecture Overview

FlowMesh follows a microservices architecture in which independent services communicate through gRPC, while asynchronous business events are processed through Redis Streams.

The API Gateway provides the entry point for client requests. PostgreSQL stores application data and outbox events, while Redis handles event streaming and worker metrics.

## Architecture Diagram

```mermaid
flowchart TB
    Client[Client Application]
    Gateway[FastAPI API Gateway]

    Order[Order Service]
    Inventory[Inventory Service]
    Delivery[Delivery Service]

    DB[(PostgreSQL)]
    Redis[(Redis Streams)]

    OrderWorker[Order Event Worker]
    DeliveryWorker[Delivery Event Worker]
    StatusWorker[Order Status Worker]

    OutboxWorker[Outbox Publishers]

    Client --> Gateway

    Gateway -->|gRPC| Order
    Gateway -->|gRPC| Inventory
    Gateway -->|gRPC| Delivery

    Order --> DB
    Inventory --> DB
    Delivery --> DB

    DB --> OutboxWorker
    OutboxWorker --> Redis

    Redis --> OrderWorker
    Redis --> DeliveryWorker
    Redis --> StatusWorker

    OrderWorker --> Delivery
    DeliveryWorker --> Order
    StatusWorker --> Order
```

## Project Structure

```text
flowmesh/
│
├── frontend/                     # Next.js frontend (initial setup)
│
├── gateway/
│   └── app/
│       └── main.py               # FastAPI API Gateway
│
├── services/
│   ├── order_service/
│   │   └── app/                  # Order service and gRPC server
│   │
│   ├── inventory_service/
│   │   └── app/                  # Inventory service and gRPC server
│   │
│   └── delivery_service/
│       └── app/                  # Delivery service and gRPC server
│
├── proto/                        # Protocol Buffer definitions
│
├── lib/
│   ├── events.py                 # Event publishing utilities
│   ├── event_reliability.py      # Retry and dead-letter handling
│   ├── logger.py                 # Structured logging
│   └── metrics.py                # Redis-backed metrics
│
├── workers/
│   ├── order_event_worker.py
│   ├── delivery_event_worker.py
│   ├── order_status_worker.py
│   ├── outbox_publisher.py
│   └── delivery_outbox_publisher.py
│
├── migrations/                   # Alembic database migrations
├── tests/                        # Automated tests
│
├── docker-compose.yml
├── alembic.ini
├── .env.example
└── README.md
```

## Reliability and Event Processing

FlowMesh implements several reliability patterns to make asynchronous event processing more resilient.

### 1. Transactional Outbox Pattern

The Outbox Pattern ensures that business data and corresponding events are persisted together in a database transaction.

- Business changes and outbox events are stored in PostgreSQL.
- Dedicated publisher workers retrieve unpublished events.
- Events are published to Redis Streams.
- Published outbox records are marked as published.
- `FOR UPDATE SKIP LOCKED` prevents multiple publishers from selecting the same records concurrently.

Because PostgreSQL and Redis do not share a distributed transaction, duplicate publication is possible if Redis accepts an event but the database update fails. Consumers use event IDs to prevent duplicate business processing.

### 2. Idempotent Event Processing

FlowMesh uses event IDs to identify previously processed events.

- A `ProcessedEvent` record tracks processed event IDs.
- Event processing and the processed-event record are committed in the same database transaction.
- Duplicate events do not create duplicate deliveries.
- Database uniqueness constraints protect against concurrent duplicate processing.

### 3. Retry Mechanism

Failed events are handled using Redis Streams consumer groups.

- Failed processing attempts are tracked using pending-message delivery information.
- Events are retried while they remain below the configured maximum.
- The maximum delivery attempts are configured as `5`.

### 4. Dead Letter Queue (DLQ)

Events that exceed the maximum delivery attempts are moved to the dead-letter stream:

`flowmesh:dead-letter-events`

The dead-letter record preserves the original event information and message ID for investigation and deduplication.

### 5. Pending Message Recovery

FlowMesh uses Redis Streams pending-entry recovery to reclaim messages that were delivered but not acknowledged.

Workers use `XAUTOCLAIM` to recover eligible pending messages and resume processing.

### 6. Graceful Worker Shutdown

Event workers handle shutdown signals using Python's `threading.Event` and signal handlers.

During shutdown:

- Workers stop fetching new messages.
- Already-fetched messages are allowed to finish processing.
- Already-claimed recovery batches are completed before stopping.

This reduces the risk of interrupting in-flight event processing.

### 7. Structured Logging

FlowMesh uses a shared logging utility that produces structured JSON logs.

Log records include:

- UTC timestamp
- Log level
- Logger name
- Message
- Additional contextual fields
- Exception details when available

This makes worker activity and failures easier to inspect.

### 8. Worker Metrics

FlowMesh maintains Redis-backed counters under the `flowmesh:metrics:` key prefix.

The admin-protected `GET /metrics` endpoint exposes:

| Metric                       | Description                                      |
| ---------------------------- | ------------------------------------------------ |
| `events_processed_total`     | Successfully processed and acknowledged events   |
| `events_failed_total`        | Failed event processing attempts                 |
| `events_retried_total`       | Events scheduled for retry                       |
| `events_dead_lettered_total` | Events moved to the dead-letter stream           |
| `events_recovered_total`     | Events reclaimed during pending-message recovery |
| `events_ack_failed_total`    | Failed message acknowledgements                  |
| `events_ack_zero_total`      | Acknowledgements where Redis returned zero       |
| `events_ack_exception_total` | Acknowledgements that raised Redis exceptions    |

The separate acknowledgement metrics help distinguish Redis acknowledgement failures from business-processing failures.

## Getting Started

Follow these steps to run FlowMesh locally.

### Prerequisites

Make sure you have the following installed:

- Python 3.12 or later
- PostgreSQL
- Redis
- Docker Desktop
- Git

### 1. Clone the Repository

```bash
git clone https://github.com/utsavanand131/flowmesh.git
cd flowmesh
```

### 2. Create and Activate a Virtual Environment

**Windows:**

```bash
python -m venv .venv
.venv\Scripts\activate
```

**Linux / macOS:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

Install the project dependencies:

```bash
pip install -r requirements.txt
```

Install any additional dependencies required by the project if they are not included above.

### 4. Configure Environment Variables

Create a `.env` file in the project root using `.env.example` as a reference.

```env
DATABASE_URL=postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/flowmesh

REDIS_URL=redis://localhost:6379/0

JWT_SECRET=YOUR_JWT_SECRET

GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback

GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=
GITHUB_REDIRECT_URI=http://localhost:8000/auth/github/callback

FRONTEND_URL=http://localhost:3001

COOKIE_SECURE=false
COOKIE_SAMESITE=lax
```

Replace placeholder values with your local configuration.

OAuth credentials are needed only when using the corresponding Google or GitHub authentication flows.

**Important:** Never commit your actual `.env` file or expose credentials in source control.

### 5. Start PostgreSQL

Make sure PostgreSQL is running and create a database named:

```sql
CREATE DATABASE flowmesh;
```

### 6. Start Redis

FlowMesh includes a Docker Compose configuration for Redis.

```bash
docker compose up -d
```

Check that the Redis container is running:

```bash
docker ps
```

### 7. Run Database Migrations

Apply the existing Alembic migrations:

```bash
alembic upgrade head
```

## Running FlowMesh

After completing the environment setup and database migrations, start the services and workers.

Keep each service running in a separate terminal.

### Terminal 1 — Redis

```bash
cd C:\projects\flowmesh
docker compose up -d
```

### Terminal 2 — Order gRPC Server

```bash
cd C:\projects\flowmesh
.venv\Scripts\activate
set PYTHONPATH=C:\projects\flowmesh
cd services\order_service\app
python grpc_server.py
```

### Terminal 3 — Inventory gRPC Server

```bash
cd C:\projects\flowmesh
.venv\Scripts\activate
set PYTHONPATH=C:\projects\flowmesh
cd services\inventory_service\app
python grpc_server.py
```

### Terminal 4 — Delivery gRPC Server

```bash
cd C:\projects\flowmesh
.venv\Scripts\activate
set PYTHONPATH=C:\projects\flowmesh
cd services\delivery_service\app
python grpc_server.py
```

### Terminal 5 — API Gateway

```bash
cd C:\projects\flowmesh
.venv\Scripts\activate
set PYTHONPATH=C:\projects\flowmesh\gateway\app
uvicorn gateway.app.main:app --reload --port 8000
```

### Terminal 6 — Order Event Worker

```bash
cd C:\projects\flowmesh
.venv\Scripts\activate
set PYTHONPATH=C:\projects\flowmesh\gateway\app;C:\projects\flowmesh\services\order_service\app;C:\projects\flowmesh\services\inventory_service\app;C:\projects\flowmesh\services\delivery_service\app
python -m workers.order_event_worker
```

### Terminal 7 — Delivery Event Worker

```bash
cd C:\projects\flowmesh
.venv\Scripts\activate
set PYTHONPATH=C:\projects\flowmesh\gateway\app;C:\projects\flowmesh\services\order_service\app;C:\projects\flowmesh\services\inventory_service\app;C:\projects\flowmesh\services\delivery_service\app
python -m workers.delivery_event_worker
```

### Terminal 8 — Order Status Worker

```bash
cd C:\projects\flowmesh
.venv\Scripts\activate
set PYTHONPATH=C:\projects\flowmesh\gateway\app;C:\projects\flowmesh\services\order_service\app;C:\projects\flowmesh\services\inventory_service\app;C:\projects\flowmesh\services\delivery_service\app
python -m workers.order_status_worker
```

### Terminal 9 — Order Outbox Publisher

```bash
cd C:\projects\flowmesh
.venv\Scripts\activate
set PYTHONPATH=C:\projects\flowmesh\gateway\app;C:\projects\flowmesh\services\order_service\app;C:\projects\flowmesh\services\inventory_service\app;C:\projects\flowmesh\services\delivery_service\app
python -m workers.outbox_publisher
```

### Terminal 10 — Delivery Outbox Publisher

```bash
cd C:\projects\flowmesh
.venv\Scripts\activate
set PYTHONPATH=C:\projects\flowmesh\gateway\app;C:\projects\flowmesh\services\order_service\app;C:\projects\flowmesh\services\inventory_service\app;C:\projects\flowmesh\services\delivery_service\app
python -m workers.delivery_outbox_publisher
```

### Accessing the API

Once the API Gateway is running, open:

- **Swagger UI:** http://localhost:8000/docs
- **OpenAPI schema:** http://localhost:8000/openapi.json
- **Worker Metrics:** `GET http://localhost:8000/metrics` (requires admin authentication)

## Testing

FlowMesh uses Pytest for automated testing.

Run the complete test suite from the project root:

```bash
pytest -v
```

The latest verified test result:

```text
170 passed, 2 warnings
```

The two warnings are existing deprecation warnings from Starlette/httpx and AnyIO.

The test suite covers:

- Order event processing
- Delivery event processing
- Order status updates
- Retry and dead-letter handling
- Pending-message recovery
- Graceful worker shutdown
- Event reliability and idempotency
- Redis-backed metrics

## Project Status

### Backend

- [x] FastAPI API Gateway
- [x] Order, Inventory, and Delivery microservices
- [x] gRPC communication
- [x] PostgreSQL persistence
- [x] Redis Streams event processing
- [x] Transactional Outbox Pattern
- [x] Idempotent event processing
- [x] Retry and Dead Letter Queue
- [x] Pending message recovery
- [x] Graceful worker shutdown
- [x] Structured JSON logging
- [x] Redis-backed worker metrics
- [x] Automated tests

### Frontend

- [ ] Next.js frontend implementation
- [ ] API integration
- [ ] Dashboard and user interface

The frontend directory currently contains the initial Next.js setup. Frontend development is planned for a later stage.

## Future Improvements

- Build the Next.js frontend and integrate it with the API Gateway.
- Add monitoring dashboards for worker metrics.
- Improve deployment and container orchestration.
- Add integration and end-to-end testing.
- Introduce production-ready observability and health monitoring.

## License

This project is currently a personal development project.
