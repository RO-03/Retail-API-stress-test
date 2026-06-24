# CI/CD Pipeline — Implementation Walkthrough

## Files Created / Modified

| File | Action |
|---|---|
| [.github/workflows/deploy.yml](file:///c:/Users/Client/Documents/project/retail_docker/.github/workflows/deploy.yml) | **NEW** — GitHub Actions pipeline |
| [tests/test_api.py](file:///c:/Users/Client/Documents/project/retail_docker/tests/test_api.py) | **NEW** — Pytest unit test suite |
| [tests/check_performance.py](file:///c:/Users/Client/Documents/project/retail_docker/tests/check_performance.py) | **NEW** — JMeter quality gate script |
| [requirements.txt](file:///c:/Users/Client/Documents/project/retail_docker/requirements.txt) | **MODIFIED** — Added `pytest`, `httpx` |

---

## Pipeline Flow

```
Push to main
    │
    ▼
[1] Checkout
    │
    ▼
[2] pip install → pytest tests/test_api.py
    │  ← Abort on any test failure
    ▼
[3] docker run justb4/jmeter → results.csv
    │
    ▼
[3b] python3 tests/check_performance.py results.csv
    │  ← Abort if error rate > 0% OR throughput < 80 RPS
    ▼
[4] eval $(minikube docker-env) && docker build -t retail-api:latest .
    │
    ▼
[5] kubectl apply -f k8s/  →  kubectl rollout restart
    │
    ▼
[6] kubectl rollout status --timeout=180s   (wait for 3/3 Ready)
    │
    ▼
[7] Upload results.csv + jmeter-report/ as pipeline artifact
```

---

## Self-Hosted Runner Setup (WSL2 Ubuntu)

Run these commands **once** inside WSL2 to configure the runner with the required permissions.

### 1 — Add runner user to docker group (no sudo for Docker)
```bash
sudo usermod -aG docker $USER
# Re-login or run:
newgrp docker
# Verify:
docker ps
```

### 2 — Give runner user passwordless kubectl access
```bash
# Minikube writes kubeconfig to ~/.kube/config
# Verify the runner can reach the cluster:
kubectl get nodes
```

### 3 — Install the GitHub Actions self-hosted runner
```bash
mkdir -p ~/actions-runner && cd ~/actions-runner
# Download runner (replace with latest URL from GitHub repo → Settings → Actions → Runners)
curl -o actions-runner-linux-x64.tar.gz -L \
  https://github.com/actions/runner/releases/download/v2.317.0/actions-runner-linux-x64-2.317.0.tar.gz
tar xzf actions-runner-linux-x64.tar.gz

# Register with your repository
./config.sh --url https://github.com/<YOUR_ORG>/<YOUR_REPO> --token <RUNNER_TOKEN>

# Start as a persistent background service
sudo ./svc.sh install
sudo ./svc.sh start
```

### 4 — Add hosts entry so JMeter can resolve retail-store.local
```bash
# WSL2 /etc/hosts (already set if you followed the Minikube setup)
echo "$(minikube ip)  retail-store.local" | sudo tee -a /etc/hosts
```

### 5 — Ensure minikube is running when the runner starts
```bash
# Optional: add to runner's ~/.bashrc or a systemd service
minikube status || minikube start --cpus=6 --memory=8192
```

---

## Local Test Commands (run inside WSL2)

### Run unit tests locally
```bash
cd /path/to/retail_docker
DATABASE_URL="sqlite:///./test_retail.db" pytest tests/test_api.py -v
```

### Dry-run JMeter locally (Docker)
```bash
docker run --rm \
  --network host \
  -v "$(pwd):/workspace" \
  -w /workspace \
  justb4/jmeter:5.6.3 \
  -n -t batches.jmx -l results.csv -j jmeter.log
```

### Evaluate results manually
```bash
python3 tests/check_performance.py results.csv
```

### Manual rolling deploy
```bash
eval $(minikube docker-env)
docker build -t retail-api:latest .
kubectl rollout restart deployment retail-api -n retail
kubectl rollout status deployment/retail-api -n retail --timeout=180s
```

---

## Quality Gates

| Gate | Threshold | Action on fail |
|---|---|---|
| Error rate | Must be **0.00 %** | `sys.exit(1)` → pipeline aborts |
| Throughput | Must be **≥ 80 RPS** | `sys.exit(1)` → pipeline aborts |

Adjust `MIN_THROUGHPUT_RPS` in [check_performance.py](file:///c:/Users/Client/Documents/project/retail_docker/tests/check_performance.py) to match your baseline.
