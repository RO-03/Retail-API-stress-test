# High-Performance Retail API

[![CI/CD Pipeline](https://github.com/RO-03/Retail-API-stress-test/actions/workflows/deploy.yml/badge.svg)](https://github.com/RO-03/Retail-API-stress-test/actions/workflows/deploy.yml)

A highly scalable, containerized REST API for retail inventory and purchasing, engineered to handle high-concurrency workloads (+10,000 concurrent requests). Built with FastAPI, PostgreSQL, and deployed on a local Kubernetes cluster (Minikube), featuring a full continuous integration and deployment (CI/CD) pipeline.

This project was specifically designed to tackle database locking bottlenecks and optimize parallel request processing through connection pooling, efficient ASGI server configuration, and Kubernetes orchestration.

## Key Features & Architecture

- **Clean Architecture (MVC):** Structured using the Model-View-Controller design pattern for maintainability and separation of concerns.
- **High-Concurrency Tuning:** Optimized Uvicorn worker counts and PostgreSQL connection pooling strategies (handling 350+ max connections).
- **Kubernetes Orchestration:** Containerized with Docker and deployed via Kubernetes (`api.yaml`, `postgres.yaml`, `ingress.yaml`) with rolling zero-downtime updates and health probes.
- **Nginx Ingress Controller:** Bypasses standard NodePort `kube-proxy` limitations, restoring high throughput under massive loads.
- **Automated CI/CD:** GitHub Actions pipeline running on a WSL2 self-hosted runner, automating testing (pytest), performance benchmarking (JMeter), Docker image building, and Minikube deployment.
- **Robust Authentication:** JWT-based authentication with bcrypt password hashing for admin endpoints.
- **Performance Tested:** Load-tested using Apache JMeter inside an isolated Docker container.

## Technology Stack

- **Backend:** FastAPI (Python 3.11), Uvicorn, Jinja2
- **Database:** PostgreSQL 15, SQLAlchemy ORM
- **Authentication:** passlib, python-jose, bcrypt
- **Containerization:** Docker
- **Orchestration:** Kubernetes (Minikube), Nginx Ingress
- **CI/CD:** GitHub Actions
- **Testing:** Pytest, HTTPX, Apache JMeter

## Project Structure

```text
├── app/
│   ├── controllers/   # Route handlers (Admin, Customer, Health)
│   ├── core/          # App config and Database setup
│   ├── models/        # SQLAlchemy ORM Models
│   ├── schemas/       # Pydantic validation schemas
│   ├── services/      # Business logic (Auth, JWT)
│   ├── views/         # Jinja2 HTML templates
│   └── main.py        # FastAPI application factory
├── k8s/               # Kubernetes deployment manifests
├── scripts/           # DB initialization scripts
├── tests/             # Pytest unit & integration tests
├── .github/workflows/ # CI/CD pipeline definitions
├── Dockerfile         # Optimized multi-worker image
└── batches.jmx        # JMeter stress test configuration
```

## Getting Started

### Prerequisites

- Docker & Docker Compose (or Docker Desktop)
- Minikube
- `kubectl`
- Python 3.11+ (for local development)

### 1. Local Kubernetes Deployment (Minikube)

First, start Minikube and enable the Nginx Ingress addon:
```bash
minikube start
minikube addons enable ingress
```

Point your Docker CLI to Minikube's internal daemon:
```bash
eval $(minikube docker-env)  # Linux/macOS
& minikube -p minikube docker-env --shell powershell | Invoke-Expression # Windows
```

Build the application image:
```bash
docker build -t retail-api:latest .
```

Deploy the database and API components:
```bash
kubectl create namespace retail
kubectl apply -f k8s/postgres.yaml -n retail
kubectl apply -f k8s/api.yaml -n retail
kubectl apply -f k8s/ingress.yaml -n retail
```

*(Note: Depending on your OS, you may need to run `minikube tunnel` and map `retail-store.local` to `127.0.0.1` in your `hosts` file to access the Ingress).*

### 2. CI/CD Pipeline

The `.github/workflows/deploy.yml` runs a complete pipeline on every push to `main` and `minikubeMVC` branches:
1. Provisions a Conda environment and runs **Pytest** with an isolated SQLite instance.
2. Runs **JMeter Load Tests** via a throwaway Docker container against Minikube.
3. Evaluates performance (Quality Gate via `check_performance.py`).
4. Builds and injects the Docker image directly into the Minikube registry.
5. Deploys via `kubectl rollout restart` with a 3-minute readiness probe timeout.

### 3. Load Testing

Load testing can be performed using the included `batches.jmx` Apache JMeter profile, configured to hit the Nginx Ingress at `retail-store.local`. It measures:
- Request Throughput (Req/sec)
- 95th Percentile Response Time
- Error Rates under 10k concurrent constraints

## Optimization Strategy

The system is mathematically tuned for its execution environment:
- **Workers:** Calculated as `CPU cores * 0.75`. The Kubernetes pods are configured for 2 Uvicorn workers each across 3 replicas (6 total workers).
- **Database Connections:** Scaled dynamically via SQLAlchemy pool sizing `(pool_size=20, max_overflow=30)` targeting a PostgreSQL database tuned to accept `max_connections=350`.
