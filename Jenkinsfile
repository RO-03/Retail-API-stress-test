// Jenkinsfile — Retail Store API CI/CD Pipeline
// Declarative syntax. Requires: Docker CLI, kubectl, and minikube on the Jenkins agent.
// Compatible with Minikube (Docker driver) on a Windows/WSL2 host.

pipeline {

    agent any

    // ── Pipeline-level environment ───────────────────────────────────────────
    environment {
        // Image name used consistently across stages
        IMAGE_NAME    = "retail-api"
        IMAGE_TAG     = "build-${env.BUILD_NUMBER}"
        IMAGE_LATEST  = "retail-api:latest"
        IMAGE_VERSIONED = "${IMAGE_NAME}:${IMAGE_TAG}"

        // Kubernetes namespace (must match what the manifests expect)
        K8S_NAMESPACE = "retail"

        // Deployment name (must match metadata.name in k8s/api.yaml)
        DEPLOYMENT    = "retail-api"

        // Container name inside the pod spec (must match spec.containers[0].name)
        CONTAINER     = "retail-api"

        // Number of replicas to verify — must match k8s/api.yaml spec.replicas
        REPLICAS      = "3"
    }

    options {
        // Keep the 10 most recent builds' artifacts and logs
        buildDiscarder(logRotator(numToKeepStr: '10'))
        // Abort the pipeline if it runs longer than 20 minutes
        timeout(time: 20, unit: 'MINUTES')
        // Do not run concurrent builds for the same branch
        disableConcurrentBuilds()
        // Add timestamps to every console log line
        timestamps()
    }

    stages {

        // ── Stage 1 — Checkout ───────────────────────────────────────────────
        stage('Checkout') {
            steps {
                echo '=== Checking out source code ==='
                // Jenkins automatically checks out the SCM configured in the job.
                // The checkout step also sets the GIT_COMMIT / GIT_BRANCH env vars.
                checkout scm

                echo "Branch  : ${env.GIT_BRANCH}"
                echo "Commit  : ${env.GIT_COMMIT}"
            }
        }

        // ── Stage 2 — Test ───────────────────────────────────────────────────
        stage('Test') {
            steps {
                echo '=== Installing dependencies and running pytest ==='

                // Use a virtualenv so we do not pollute the agent's system Python.
                // The `python3 -m venv` approach works on both Linux agents and
                // WSL2-backed Jenkins containers.
                sh '''
                    python3 -m venv .ci_venv
                    . .ci_venv/bin/activate

                    # Upgrade pip silently
                    pip install --quiet --upgrade pip

                    # Install all runtime + test dependencies
                    pip install --quiet -r requirements.txt

                    # Run the test suite.
                    # -v      : verbose output (each test name + pass/fail)
                    # --tb=short : compact traceback on failure
                    # --junitxml : machine-readable results for Jenkins JUnit plugin
                    pytest tests/ -v --tb=short --junitxml=test-results.xml
                '''
            }

            post {
                always {
                    // Publish JUnit results so Jenkins shows a Test Trend graph
                    junit allowEmptyResults: true, testResults: 'test-results.xml'
                }
                failure {
                    echo 'Tests FAILED — aborting pipeline. Fix failing tests before re-running.'
                }
            }
        }

        // ── Stage 3 — Build ──────────────────────────────────────────────────
        stage('Build') {
            steps {
                echo '=== Building Docker image inside Minikube\'s daemon ==='

                // Point the Docker CLI at Minikube's internal daemon.
                // This is the critical step that makes the built image immediately
                // available to the K8s cluster WITHOUT pushing to a remote registry.
                //
                // The Jenkins container must have:
                //   • DOCKER_HOST set  — OR —
                //   • /var/run/docker.sock mounted  — AND —
                //   • minikube binary present and the kubeconfig mounted at ~/.kube/config
                sh '''
                    # Re-point Docker CLI at Minikube's internal daemon for this shell.
                    # Using eval because "minikube docker-env" emits export statements.
                    eval $(minikube docker-env)

                    echo "Building ${IMAGE_VERSIONED} ..."
                    docker build \
                        --tag "${IMAGE_VERSIONED}" \
                        --tag "${IMAGE_LATEST}" \
                        --label "build.number=${BUILD_NUMBER}" \
                        --label "git.commit=${GIT_COMMIT}" \
                        .

                    echo "Image layers:"
                    docker history "${IMAGE_VERSIONED}" --no-trunc --format "{{.Size}}\\t{{.CreatedBy}}" | head -10
                '''
            }
        }

        // ── Stage 4 — Deploy ─────────────────────────────────────────────────
        stage('Deploy') {
            steps {
                echo '=== Triggering Kubernetes Rolling Update ==='

                sh '''
                    # Verify the namespace exists; create it if it doesn't.
                    kubectl get namespace "${K8S_NAMESPACE}" > /dev/null 2>&1 || \
                        kubectl create namespace "${K8S_NAMESPACE}"

                    # Apply the latest manifests (idempotent — safe to run every time).
                    # This also picks up any YAML changes committed alongside the code.
                    kubectl apply -f k8s/postgres.yaml -n "${K8S_NAMESPACE}"
                    kubectl apply -f k8s/api.yaml      -n "${K8S_NAMESPACE}"
                    kubectl apply -f k8s/ingress.yaml  -n "${K8S_NAMESPACE}"

                    # Update the container image in the Deployment.
                    # kubectl set image automatically triggers a RollingUpdate because
                    # the Deployment's spec.strategy.type = RollingUpdate (from api.yaml).
                    kubectl set image \
                        deployment/"${DEPLOYMENT}" \
                        "${CONTAINER}=${IMAGE_VERSIONED}" \
                        -n "${K8S_NAMESPACE}"

                    echo "Rolling update triggered — image set to ${IMAGE_VERSIONED}"
                    kubectl rollout history deployment/"${DEPLOYMENT}" -n "${K8S_NAMESPACE}" | tail -5
                '''
            }
        }

        // ── Stage 5 — Verify ─────────────────────────────────────────────────
        stage('Verify') {
            steps {
                echo '=== Verifying rolling update and health probes ==='

                sh '''
                    # Block until all replicas are Running and passing their /health
                    # readiness probes.  Fails (non-zero exit) if rollout takes longer
                    # than 3 minutes, which triggers a pipeline failure.
                    kubectl rollout status \
                        deployment/"${DEPLOYMENT}" \
                        -n "${K8S_NAMESPACE}" \
                        --timeout=180s

                    echo "Rollout complete. Verifying ${REPLICAS} ready replicas..."

                    READY=$(kubectl get deployment "${DEPLOYMENT}" \
                        -n "${K8S_NAMESPACE}" \
                        -o jsonpath="{.status.readyReplicas}")

                    echo "Ready replicas: ${READY} / ${REPLICAS}"

                    if [ "${READY}" != "${REPLICAS}" ]; then
                        echo "ERROR: Expected ${REPLICAS} ready replicas, found ${READY}."
                        kubectl get pods -n "${K8S_NAMESPACE}" -l app=retail-api
                        kubectl describe deployment "${DEPLOYMENT}" -n "${K8S_NAMESPACE}"
                        exit 1
                    fi

                    echo "All ${REPLICAS} replicas are healthy."

                    # Final smoke test via the Ingress (requires minikube tunnel
                    # to be running on the host for this to resolve).
                    # Falls back gracefully if the tunnel is not active.
                    INGRESS_IP=$(kubectl get ingress retail-api-ingress \
                        -n "${K8S_NAMESPACE}" \
                        -o jsonpath="{.status.loadBalancer.ingress[0].ip}" 2>/dev/null || true)

                    if [ -n "${INGRESS_IP}" ]; then
                        echo "Smoke-testing /health via Ingress IP ${INGRESS_IP} ..."
                        HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
                            --resolve "retail-store.local:80:${INGRESS_IP}" \
                            http://retail-store.local/health --max-time 10 || echo "000")
                        echo "HTTP status: ${HTTP_STATUS}"
                        if [ "${HTTP_STATUS}" != "200" ]; then
                            echo "WARNING: /health smoke test returned ${HTTP_STATUS}. Check Ingress routing."
                        fi
                    else
                        echo "Ingress IP not yet assigned — skipping smoke test (run minikube tunnel on the host)."
                    fi
                '''
            }

            post {
                failure {
                    // Dump pod state to help diagnose failures
                    sh '''
                        echo "=== Pod status ==="
                        kubectl get pods -n "${K8S_NAMESPACE}" -l app=retail-api -o wide || true

                        echo "=== Pod events (last 20) ==="
                        kubectl get events -n "${K8S_NAMESPACE}" --sort-by=.lastTimestamp | tail -20 || true

                        echo "=== Rolling back to previous revision ==="
                        kubectl rollout undo deployment/"${DEPLOYMENT}" -n "${K8S_NAMESPACE}" || true
                    '''
                }
            }
        }
    }

    // ── Post-pipeline notifications ──────────────────────────────────────────
    post {
        success {
            echo """
╔══════════════════════════════════════════════════════╗
║  ✅  Pipeline SUCCEEDED                              ║
║  Build  : #${env.BUILD_NUMBER}                       ║
║  Image  : ${IMAGE_VERSIONED}                         ║
║  Branch : ${env.GIT_BRANCH}                          ║
╚══════════════════════════════════════════════════════╝
"""
        }

        failure {
            echo """
╔══════════════════════════════════════════════════════╗
║  ❌  Pipeline FAILED                                 ║
║  Build  : #${env.BUILD_NUMBER}                       ║
║  Check the console output above for details.         ║
╚══════════════════════════════════════════════════════╝
"""
        }

        always {
            // Clean up the Python virtualenv to keep the workspace tidy.
            // The .ci_venv directory can grow large across many builds.
            sh 'rm -rf .ci_venv test-results.xml test_retail.db || true'

            echo "Workspace cleaned. Pipeline finished."
        }
    }
}
