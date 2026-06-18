# FastAPI Retail Store API – Performance Optimization & Load Testing Guide

## Project Overview

This is a full-stack Retail Store Inventory and Purchasing API designed for high concurrency workloads (10,000+ requests).

To eliminate SQLite file-locking bottlenecks and enable true parallel request processing, the application has been migrated to PostgreSQL. This allows multiple Uvicorn workers to operate efficiently using shared database access and connection pooling.

---

# Technology Stack

| Component      | Technology                            |
| -------------- | ------------------------------------- |
| Framework      | FastAPI (Python 3.11)                 |
| ASGI Server    | Uvicorn                               |
| ORM            | SQLAlchemy (Synchronous)              |
| Database       | PostgreSQL 15 (Official Alpine Image) |
| Infrastructure | Docker Compose                        |
| Load Testing   | Apache JMeter                         |

---

# Infrastructure Files

## `docker-compose.yml`

Defines two services:

### `db`

* Uses `postgres:15-alpine`
* Stores data in persistent volume `postgres_data`
* Initializes PostgreSQL credentials
* Configures PostgreSQL connection limits

### `api`

* Builds FastAPI backend image
* Injects `DATABASE_URL`
* Exposes port `8000`
* Depends on the database service

---

## `Dockerfile`

Runs FastAPI using multiple Uvicorn workers.

### Worker Calculation Formula

```text
workers = CPU cores × 0.75
```

### Example

For an 8-core machine:

```text
workers = 8 × 0.75 = 6
```

### Uvicorn Configuration

```dockerfile
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "<calculated_workers>"]
```

---

## `docker-compose.yml`

### PostgreSQL Connection Calculation

```text
max_connections = workers × 5 + 50
```

### Example

For 60 workers:

```text
max_connections = 60 × 5 + 50
                 = 350
```

### PostgreSQL Configuration

```yaml
services:
  db:
    image: postgres:15-alpine
    command: postgres -c max_connections=350
    environment:
      ...............
```

---

## `database.py`

SQLAlchemy engine configuration:

```python
engine = create_engine(
    DATABASE_URL,
    pool_size=20,        # 20 base connections per worker
    max_overflow=30,     # +30 overflow = 50 max connections per worker
    pool_timeout=30,
    pool_recycle=1800
)
```

### Connection Pool Settings

| Parameter    | Value    | Description                      |
| ------------ | -------- | -------------------------------- |
| pool_size    | 20       | Base connections per worker      |
| max_overflow | 30       | Additional temporary connections |
| pool_timeout | 30 sec   | Wait time before timeout         |
| pool_recycle | 1800 sec | Recycle stale connections        |

Maximum possible connections per worker:

```text
20 + 30 = 50 connections
```

---

## `requirements.txt`

Key dependencies:

```text
fastapi
uvicorn
sqlalchemy
pydantic
requests
psycopg2-binary
```

---

# Apache JMeter Setup

Install Apache JMeter and use the provided:

```text
batches.jmx
```

file for load testing and performance tuning.

### Steps

1. Install JMeter
2. Launch JMeter
3. Open:

```text
batches.jmx
```

4. Configure test parameters if required
5. Execute the stress test
6. Collect performance metrics

---

# Optimization Workflow

## Step 1 – Calculate Worker Count

```text
workers = CPU cores × 0.75
```

---

## Step 2 – Configure PostgreSQL Connections

```text
max_connections = workers × 5 + 50
```

---

## Step 3 – Deploy Application

```bash
docker compose up -d --build
```

---

## Step 4 – Run JMeter Stress Tests

Open:

```text
batches.jmx
```

Run load tests and simulate production traffic.

---

## Step 5 – Record Metrics

Capture the following:

### Application Metrics

* Throughput (Requests/sec)
* Average Response Time
* 95th Percentile Response Time
* Error Rate

### System Metrics

* CPU Usage
* Memory Usage
* Network Usage

### Database Metrics

* Active Connections
* Connection Pool Utilization
* Query Performance

---

## Step 6 – Tune Worker Count

Repeat testing with different worker values.

### Increase Workers If

* CPU utilization is low
* Database has available connections
* Throughput increases

### Decrease Workers If

* Context switching becomes excessive
* CPU remains saturated
* Response times worsen
* Error rates increase

---

## Step 7 – Select Optimal Configuration

Choose the configuration that provides:

### Highest Throughput

Maximum requests processed per second.

### Lowest Response Time

Fastest average and percentile response times.

### Stable CPU Utilization

Avoids CPU saturation and excessive context switching.

### Minimal Errors

Maintains reliability under heavy load.

---

# Standard Commands

## Build and Start

```bash
docker compose up -d --build
```

---

## View Logs

```bash
docker compose logs -f
```

---

## Stop Containers

```bash
docker compose down
```

---

## Restart Services

```bash
docker compose restart
```

---

## Check Running Containers

```bash
docker compose ps
```

---

# Summary

1. Calculate workers:

```text
workers = CPU cores × 0.75
```

2. Configure PostgreSQL:

```text
max_connections = workers × 5 + 50
```

3. Deploy:

```bash
docker compose up -d --build
```

4. Run:

```text
batches.jmx
```

5. Measure:

   * Throughput
   * Response Time
   * Error Rate
   * CPU Usage
   * Database Connections

6. Adjust worker count and repeat testing.

7. Select the configuration with the best balance of:

   * Throughput
   * Latency
   * Stability
   * Resource Utilization
