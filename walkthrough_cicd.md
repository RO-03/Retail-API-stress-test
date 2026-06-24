# CI/CD Pipeline Walkthrough — Jenkins + Minikube

## What Was Delivered

| Deliverable | File |
|---|---|
| pytest test suite | [`tests/test_api.py`](file:///c:/Users/Client/Documents/project/retail_docker/tests/test_api.py) |
| Declarative Jenkinsfile | [`Jenkinsfile`](file:///c:/Users/Client/Documents/project/retail_docker/Jenkinsfile) |
| Jenkins Docker Compose | [`docker-compose.jenkins.yml`](file:///c:/Users/Client/Documents/project/retail_docker/docker-compose.jenkins.yml) |
| Jenkins custom Dockerfile | [`jenkins.Dockerfile`](file:///c:/Users/Client/Documents/project/retail_docker/jenkins.Dockerfile) |
| Jenkins plugin list | [`jenkins-plugins.txt`](file:///c:/Users/Client/Documents/project/retail_docker/jenkins-plugins.txt) |
| Updated requirements | [`requirements.txt`](file:///c:/Users/Client/Documents/project/retail_docker/requirements.txt) |

---

## Architecture

```
  Windows / WSL2 Host
  ┌─────────────────────────────────────────────────────────┐
  │                                                         │
  │  Docker Engine (/var/run/docker.sock)                   │
  │       │                                                 │
  │  ┌────┴──────────────────────────┐                      │
  │  │  jenkins-retail container     │                      │
  │  │  • Jenkins LTS (JDK 21)       │                      │
  │  │  • Docker CLI (host socket)   │                      │
  │  │  • kubectl  → ~/.kube/config  │                      │
  │  │  • minikube CLI               │                      │
  │  │  • Python 3 + venv            │                      │
  │  │                               │                      │
  │  │  Port 8080 ─► localhost:8080  │                      │
  │  └───────────────────────────────┘                      │
  │                                                         │
  │  Minikube (Docker driver)                               │
  │  ┌──────────────────────────────────────────────┐       │
  │  │  retail namespace                            │       │
  │  │  • retail-api  (3 replicas, RollingUpdate)  │       │
  │  │  • postgres    (1 replica)                  │       │
  │  │  • Nginx Ingress → retail-store.local        │       │
  │  └──────────────────────────────────────────────┘       │
  └─────────────────────────────────────────────────────────┘
```

---

## Part 1 — Spin Up the Jenkins Container

### Step 1 — Start Minikube first (required for kubeconfig and minikube docker-env)

```powershell
minikube start --cpus=6 --memory=8192 --driver=docker
```

### Step 2 — Build and start the Jenkins container

```powershell
# From the project root (where docker-compose.jenkins.yml lives)
docker compose -f docker-compose.jenkins.yml up -d --build
```

> [!NOTE]
> The first build takes ~3–5 minutes because it installs Docker CLI, kubectl, minikube, Python 3, and the Jenkins plugins inside the image. Subsequent starts are instant.

### Step 3 — Retrieve the initial admin password

```powershell
docker exec jenkins-retail cat /var/jenkins_home/secrets/initialAdminPassword
```

### Step 4 — Open the Jenkins UI

Navigate to **http://localhost:8080** and paste the password from Step 3.

> [!TIP]
> Because `JAVA_OPTS=-Djenkins.install.runSetupWizard=false` is set, the setup wizard is skipped and all plugins from `jenkins-plugins.txt` are pre-installed.
> You can still change the admin password at **Manage Jenkins → Security → Users**.

---

## Part 2 — Create the Pipeline Job

### Step 1 — New Item

1. Click **"New Item"** on the Jenkins dashboard.
2. Enter name: **`retail-api-pipeline`**
3. Select **"Pipeline"**
4. Click **OK**.

### Step 2 — Configure the Pipeline source

Under the **Pipeline** section at the bottom of the job configuration:

| Setting | Value |
|---|---|
| **Definition** | Pipeline script from SCM |
| **SCM** | Git |
| **Repository URL** | `file:///path/to/retail_docker` *(local)* or your Git remote URL |
| **Branch Specifier** | `*/main` (or your branch name) |
| **Script Path** | `Jenkinsfile` |

Click **Save**.

### Step 3 — Run the pipeline

Click **"Build Now"** on the job page.

The pipeline will execute all 5 stages and you can watch progress in **Blue Ocean** or the classic stage view.

---

## Part 3 — Pipeline Stages Explained

### Stage 1 — Checkout
Pulls the latest code from the configured Git remote. Sets `GIT_BRANCH` and `GIT_COMMIT` environment variables used for image labels.

### Stage 2 — Test
```
python3 -m venv .ci_venv
pytest tests/ -v --tb=short --junitxml=test-results.xml
```
- Runs inside a temporary venv to isolate dependencies.
- Uses **in-memory SQLite** — no running Postgres needed.
- Publishes JUnit XML results → Jenkins shows a **Test Trend** graph.
- **Pipeline aborts immediately if any test fails.**

### Stage 3 — Build
```bash
eval $(minikube docker-env)
docker build -t retail-api:build-<N> -t retail-api:latest .
```
- `minikube docker-env` re-points the Docker CLI at Minikube's internal daemon.
- The image is built **inside the cluster** — no Docker Hub push needed.
- Tagged with both `latest` and a build-number tag for rollback traceability.

### Stage 4 — Deploy
```bash
kubectl apply -f k8s/postgres.yaml -n retail
kubectl apply -f k8s/api.yaml      -n retail
kubectl apply -f k8s/ingress.yaml  -n retail
kubectl set image deployment/retail-api retail-api=retail-api:build-<N> -n retail
```
- `kubectl apply` is idempotent — safe to run on every build.
- `kubectl set image` triggers a **RollingUpdate** (`maxSurge:1`, `maxUnavailable:0`) with zero dropped traffic.

### Stage 5 — Verify
```bash
kubectl rollout status deployment/retail-api -n retail --timeout=180s
```
- Blocks until all **3 replicas** pass their `/health` readiness probes.
- Asserts `readyReplicas == 3`.
- Optional `/health` smoke test via the Ingress IP.
- **Auto-rollback** (`kubectl rollout undo`) if this stage fails.

---

## Part 4 — Test Suite Coverage

| Test class | What it covers |
|---|---|
| `TestHealth` | `GET /health` returns 200 + `{"status":"ok"}` |
| `TestPublicRoutes` | `GET /items`, `POST /purchase/{id}` (success, out-of-stock, nonexistent) |
| `TestAdminAuth` | Login success/failure, protected route with/without token |
| `TestAdminCRUD` | Add, update price, restock, delete items; 404 cases |

Run locally:
```powershell
# From project root
pip install -r requirements.txt
pytest tests/ -v
```

---

## Part 5 — Triggering Builds Automatically (optional)

To trigger a pipeline run on every `git push`:

1. **Local Git hook** — add a `post-commit` hook that calls the Jenkins REST API:
   ```bash
   curl -X POST http://localhost:8080/job/retail-api-pipeline/build \
        --user admin:<API_TOKEN>
   ```
2. **GitHub webhook** — configure `http://<jenkins-host>:8080/github-webhook/` in your GitHub repo settings (requires the GitHub plugin, already in `jenkins-plugins.txt`).

---

## Part 6 — Teardown

```powershell
# Stop Jenkins without deleting data
docker compose -f docker-compose.jenkins.yml stop

# Stop Jenkins AND delete the jenkins_home volume (loses all jobs/history)
docker compose -f docker-compose.jenkins.yml down -v
```
