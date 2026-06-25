

---

### 📋 PROJECT MASTER CONTEXT: High-Concurrency Retail API & Hybrid-Cloud CI/CD

**1. Project Overview & Objective**
The objective is to build, test, and deploy a high-concurrency Retail Store API using a modern, enterprise-grade DevOps architecture. The project simulates a "Hybrid-Cloud" environment where cloud-based orchestration (GitHub Actions) securely triggers zero-downtime deployments to a local Kubernetes cluster.

* **Environment:** Windows 11 host operating entirely through WSL2 (Ubuntu 24.04 LTS). Standard Windows binaries are bypassed to prevent pathing issues.

**2. Tech Stack & Core Technologies**

* **Backend:** Python 3.11, FastAPI, Uvicorn (6 workers across 3 pods), SQLAlchemy, Pydantic.
* **Databases:** PostgreSQL 15 (Stateful K8s Deployment with PVC) for production; in-memory SQLite for Pytest isolation.
* **Quality & Testing:** Pytest, JMeter (executed via throwaway Docker containers), custom Python evaluation scripts.
* **Containerization & Orchestration:** Docker, Kubernetes (Minikube with 6 CPUs, 8GB RAM, Docker driver).
* **Networking:** Nginx Ingress Controller routing the custom domain `retail-store.local`.
* **CI/CD:** GitHub Actions via a Self-Hosted Linux Runner operating natively inside the WSL2 Ubuntu environment.

**3. Repository Structure**

```text
/
├── main.py, database.py, models.py, schemas.py, auth.py
├── create_admin.py, seed_items.py (DB initialization)
├── requirements.txt (Includes httpx2 to prevent Starlette deprecation warnings)
├── Dockerfile
├── k8s/
│   ├── postgres.yaml (PVC, Deployment, ClusterIP Service)
│   ├── api.yaml (Deployment with 3 replicas, ClusterIP Service, imagePullPolicy: Never)
│   └── ingress.yaml (Nginx Ingress routing to retail-store.local:80)
├── tests/
│   ├── test_api.py (Pytest suite)
│   └── check_performance.py (Evaluates JMeter CSV logs)
├── batches.jmx (Vanilla JMeter Stress Test Plan - Native Thread Groups)
└── .github/workflows/deploy.yml (The CI/CD Pipeline)

```

**4. The CI/CD Pipeline Architecture (`deploy.yml`)**
The pipeline runs sequentially on the self-hosted runner inside WSL2.

* **Step 1 & 2 (Environment & Unit Tests):** Bypasses Ubuntu 24.04's strict PEP-668 limits by sourcing a `retail-test` Miniconda environment. Executes `pytest` with `PYTHONPATH=.` to resolve root module imports.
* **Step 3 (Load Testing):** Spawns `qainsights/jmeter:latest` via Docker. Mounts the workspace to run `batches.jmx`. **Crucial K8s Networking:** Uses `--network host` and dynamically injects `--add-host retail-store.local:$(minikube ip)` so the container can resolve the Ingress domain without relying on the host's `/etc/hosts` file.
* **Step 4 (Quality Gates):** Custom script ensures 0% error rate and ≥80 RPS throughput.
* **Step 5 (Build):** Links the terminal to Minikube's internal Docker daemon (`eval $(minikube docker-env)`) and builds `retail-api:latest` directly into the K8s node, eliminating the need for an external container registry.
* **Step 6 & 7 (Deploy & Verify):** Applies K8s manifests, triggers `kubectl rollout restart`, and polls the `/health` endpoints until all 3 replicas are ready. Uploads JMeter artifacts.

**5. Current System State & Known Constraints**

* **Status:** Highly stable and fully operational.
* **Performance:** Validated to handle 200 concurrent users via JMeter with a 99.9% success rate (~240+ RPS). Occasional, solitary `502 Bad Gateway` errors may occur during absolute peak concurrency surges due to Uvicorn worker saturation at the Ingress layer.
* **JMeter Constraints:** The `batches.jmx` file strictly utilizes native JMeter `<ThreadGroup>` components. Third-party plugins (like Ultimate Thread Group) are explicitly excluded to maintain compatibility with the lightweight CI/CD Docker runner.
* **Local Access:** For manual testing from the host machine, traffic is routed bypassing the Minikube IP via a direct port-forward: `kubectl port-forward -n ingress-nginx service/ingress-nginx-controller 8080:80`. Requests must include the Host header (e.g., `curl -H "Host: retail-store.local" http://localhost:8080/health`).

---

Is there a specific area of the pipeline or the FastApi code you are planning to focus on next?