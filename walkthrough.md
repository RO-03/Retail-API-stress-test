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

---

## Phase 2 — Nginx Ingress Migration

**Motivation:** NodePort routes traffic through kube-proxy/iptables, capping throughput at ~146 req/sec under 10k concurrent JMeter users. Replacing it with an Nginx Ingress Controller bypasses kube-proxy for direct upstream load balancing, recovering the 270+ req/sec baseline.

---

### Changes Made

#### `k8s/api.yaml` — Service converted to ClusterIP
```diff
-  type: NodePort
-  ports:
-    - port: 80
-      targetPort: 8000
-      nodePort: 30000
+  type: ClusterIP
+  ports:
+    - port: 8000
+      targetPort: 8000
```
Direct external access removed. All traffic now **must** pass through the Nginx proxy.

#### `k8s/ingress.yaml` — [NEW] Routing manifest
| Field | Value |
|---|---|
| `ingressClassName` | `nginx` (Minikube addon) |
| `host` | `retail-store.local` |
| `path` | `/` (Prefix) |
| `backend.service.name` | `retail-api-service` |
| `backend.service.port` | `8000` |
| Key annotations | keepalive-connections: 64, proxy-buffering: off |

---

### Deploy Steps

#### Step 1 — Enable the Nginx Ingress addon
```powershell
minikube addons enable ingress

# Wait for the controller pod to be Running (~60s)
kubectl get pods -n ingress-nginx -w
```

#### Step 2 — Apply the updated manifests
```powershell
# Re-apply api.yaml to switch the Service type to ClusterIP
kubectl apply -f k8s/api.yaml -n retail

# Deploy the new Ingress routing rules
kubectl apply -f k8s/ingress.yaml -n retail
```

#### Step 3 — Verify the Ingress is assigned
```powershell
kubectl get ingress -n retail
# Expected output:
# NAME                 CLASS   HOSTS               ADDRESS        PORTS   AGE
# retail-api-ingress   nginx   retail-store.local   192.168.49.2   80      30s
```

#### Step 4 — Update the Windows hosts file (DNS mapping)
Run **PowerShell as Administrator**:
```powershell
# Get the Minikube IP
$minikubeIp = minikube ip

# Append the mapping to the Windows hosts file
Add-Content -Path "C:\Windows\System32\drivers\etc\hosts" -Value "`n$minikubeIp`tretail-store.local"

# Verify
Get-Content "C:\Windows\System32\drivers\etc\hosts" | Select-String "retail-store"
```

#### Step 5 — Smoke test
```powershell
# Test via curl (bypasses browser DNS cache)
curl http://retail-store.local/health
# Expected: {"status":"ok"}

curl http://retail-store.local/docs
# Expected: 200 with Swagger UI HTML
```

---

### JMeter Configuration (10k concurrent users)

Update **HTTP Request Defaults** in your JMeter test plan:

| Setting | Old Value | New Value |
|---|---|---|
| **Protocol** | `http` | `http` |
| **Server Name or IP** | `192.168.49.2` or `127.0.0.1` | `retail-store.local` |
| **Port Number** | `30000` | `80` |

> [!TIP]
> If JMeter cannot resolve `retail-store.local`, add a DNS Cache Manager element to the test plan and set it to clear per iteration, or run JMeter from WSL2 where the hosts file is shared.

---

### Updated Architecture Diagram

```
                                    ┌──────────────────────────────────────────────┐
                                    │              Kubernetes Cluster               │
                                    │                                               │
 retail-store.local:80 ────────────►│  [Nginx Ingress Controller]                  │
   (via hosts file mapping          │    - ingressClassName: nginx                 │
    to Minikube IP)                 │    - host: retail-store.local                │
                                    │    - path: / → retail-api-service:8000       │
                                    │                   │                           │
                                    │        ClusterIP Service (port 8000)          │
                                    │                   │                           │
                                    │   ┌───────────────┼───────────────┐          │
                                    │   ▼               ▼               ▼          │
                                    │ [Pod 1]        [Pod 2]        [Pod 3]        │
                                    │ 2 workers      2 workers      2 workers      │
                                    │       = 6 total Uvicorn workers               │
                                    │                   │                           │
                                    │     ClusterIP Service (db:5432)               │
                                    │                   │                           │
                                    │           [Postgres Pod]                      │
                                    │        max_connections=350                    │
                                    │           PVC (2Gi)                           │
                                    └──────────────────────────────────────────────┘
```

