# jenkins.Dockerfile
#
# Extends the official Jenkins LTS image with:
#   • Docker CLI  — so the pipeline can run `docker build` / `docker push`
#   • kubectl     — so the pipeline can run `kubectl apply` / `kubectl rollout`
#   • minikube    — so the pipeline can run `minikube docker-env` to point at
#                   the cluster's internal daemon (no remote registry needed)
#   • Python 3    — so the Test stage can create a venv and run pytest
#
# Build (handled automatically by docker-compose.jenkins.yml):
#   docker build -f jenkins.Dockerfile -t jenkins-retail .

FROM jenkins/jenkins:lts-jdk21

# ── Switch to root to install system packages ──────────────────────────────
USER root

# ── System packages ─────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        # Python 3 + venv support for the Test stage
        python3 \
        python3-pip \
        python3-venv \
        # Utilities needed by install scripts below
        curl \
        ca-certificates \
        gnupg \
        lsb-release \
        apt-transport-https \
    && rm -rf /var/lib/apt/lists/*

# ── Docker CLI ───────────────────────────────────────────────────────────────
# We install ONLY the CLI (not the daemon); the daemon lives on the host and
# is reached through the /var/run/docker.sock mount.
RUN install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg \
       | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && chmod a+r /etc/apt/keyrings/docker.gpg \
    && echo \
       "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
        https://download.docker.com/linux/debian \
        $(lsb_release -cs) stable" \
       > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        docker-ce-cli \
    && rm -rf /var/lib/apt/lists/*

# ── kubectl ───────────────────────────────────────────────────────────────────
# Install the latest stable release from the official Kubernetes apt repo.
RUN curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.30/deb/Release.key \
       | gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg \
    && echo \
       "deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] \
        https://pkgs.k8s.io/core:/stable:/v1.30/deb/ /" \
       > /etc/apt/sources.list.d/kubernetes.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends kubectl \
    && rm -rf /var/lib/apt/lists/*

# ── minikube CLI ─────────────────────────────────────────────────────────────
# Used only for `minikube docker-env` to obtain the in-cluster Docker socket
# and TLS credentials.  The actual Minikube cluster runs on the host.
RUN curl -fsSL \
       "https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64" \
       -o /usr/local/bin/minikube \
    && chmod +x /usr/local/bin/minikube

# ── Docker group + socket permissions ────────────────────────────────────────
# Ensure the jenkins user can access the Docker socket mounted from the host.
# The host socket is typically owned by the "docker" group (GID 999 on most
# Docker Desktop / Desktop Engine installations).  We add jenkins to that group.
RUN groupadd -f docker && usermod -aG docker jenkins

# ── kubeconfig permissions ────────────────────────────────────────────────────
# The kubeconfig is mounted at /root/.kube — we symlink it to jenkins' home
# so kubectl picks it up automatically when running as the jenkins user.
RUN mkdir -p /var/jenkins_home/.kube \
    && ln -sf /root/.kube/config /var/jenkins_home/.kube/config || true

# ── Switch back to the jenkins user ──────────────────────────────────────────
USER jenkins

# ── Pre-install the recommended Jenkins plugins ───────────────────────────────
# jenkins-plugin-cli is bundled with jenkins/jenkins:lts; it reads the file
# and installs plugins during the image build, avoiding first-run delays.
COPY jenkins-plugins.txt /usr/share/jenkins/ref/plugins.txt
RUN jenkins-plugin-cli --plugin-file /usr/share/jenkins/ref/plugins.txt
