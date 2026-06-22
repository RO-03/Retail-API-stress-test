# K8s Migration Walkthrough — Retail Store API

## What Was Done

### 1. `Dockerfile` — Worker Count Reduced to 2
```diff
-# Added --workers 4 to spawn multiple processes
-CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "6"]
+# K8s: 3 pods x 2 workers = 6 total system workers (stress-tested optimum)
+CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
```
Each pod runs 2 workers → 3 pods = 6 total, matching the JMeter-validated optimum.

---

### 2. `main.py` — `/health` Endpoint Added
```python
@app.get("/health", tags=["health"])
def health_check(db: Session = Depends(auth.get_db)):
    """K8s readiness & liveness probe — verifies app and DB connectivity."""
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"DB unavailable: {e}")
```
- Checks real DB connectivity (not just process liveness).
- Returns `200 {"status": "ok"}` when healthy, `503` if Postgres is unreachable.

---

### 3. `k8s/postgres.yaml` — Database Layer
| Resource | Detail |
|---|---|
| `PersistentVolumeClaim` | 2Gi, ReadWriteOnce |
| `Deployment` | 1 replica, `postgres:15-alpine`, `command: postgres -c max_connections=350` |
| `Service` | ClusterIP named **`db`** on port `5432` (API pods resolve via hostname `db`) |

---

### 4. `k8s/api.yaml` — API Layer
| Resource | Detail |
|---|---|
| `Deployment` | **3 replicas**, `RollingUpdate` (`maxSurge:1`, `maxUnavailable:0`) |
| Probes | `readinessProbe` + `livenessProbe` on `GET /health:8000` |
| Resources | `requests: 250m CPU / 256Mi RAM`, `limits: 500m CPU / 512Mi RAM` |
| `Service` | NodePort `30000 → 8000` |

---

## Deploy Commands

### Step 1 — Build & Load the Image

**Minikube:**
```powershell
# Point Docker CLI at Minikube's daemon so the image is available inside the cluster
minikube start
& minikube -p minikube docker-env --shell powershell | Invoke-Expression

docker build -t retail-api:latest .
```

**Docker Desktop (K8s enabled):**
```powershell
docker build -t retail-api:latest .
# Image is automatically available to the local cluster
```

---

### Step 2 — Apply the Manifests

```powershell
# Create namespace (optional but recommended)
kubectl create namespace retail

# Apply both manifests
kubectl apply -f k8s/postgres.yaml -n retail
kubectl apply -f k8s/api.yaml      -n retail
```

---

### Step 3 — Verify the Rollout

```powershell
# Watch all pods come up
kubectl get pods -n retail -w

# Confirm 3 API pods and 1 Postgres pod are Running
kubectl get deployments -n retail

# Check the NodePort service
kubectl get svc -n retail
```

---

### Step 4 — Access the App

**For Docker Desktop K8s:**
Navigate directly to: `http://localhost:30000`

**For Minikube (Windows with Docker Driver):**
Because Minikube runs inside a Docker container on Windows, the internal Node IP (`192.168.49.2`) is isolated and not directly routable from your host browser.
You must run the following command in a **separate terminal** to create an SSH tunnel:
```powershell
minikube service retail-api-service -n retail
```
Minikube will automatically open your browser to a newly bound `localhost` port (e.g., `http://127.0.0.1:53484`) that is tunneled directly to the API! Leave that terminal open as long as you need access.

---

### Step 5 — Trigger a Zero-Downtime Rolling Update

After changing code, rebuild the image with a new tag and update the deployment:
```powershell
docker build -t retail-api:v2 .

# Update the deployment image (triggers RollingUpdate automatically)
kubectl set image deployment/retail-api retail-api=retail-api:v2 -n retail

# Watch the rolling update in real time
kubectl rollout status deployment/retail-api -n retail
```

To roll back if something goes wrong:
```powershell
kubectl rollout undo deployment/retail-api -n retail
```

---

## Architecture Diagram

```
                        ┌─────────────────────────────────────────┐
                        │          Kubernetes Cluster              │
                        │                                          │
  localhost:30000 ──────┤  NodePort Service (retail-api-service)  │
                        │            port 30000 → 8000             │
                        │                   │                       │
                        │   ┌───────────────┼───────────────┐      │
                        │   ▼               ▼               ▼      │
                        │ [Pod 1]        [Pod 2]        [Pod 3]    │
                        │ 2 workers      2 workers      2 workers  │
                        │       = 6 total Uvicorn workers           │
                        │                   │                       │
                        │     ClusterIP Service (db:5432)           │
                        │                   │                       │
                        │           [Postgres Pod]                  │
                        │        max_connections=350                │
                        │           PVC (2Gi)                       │
                        └─────────────────────────────────────────┘
```
