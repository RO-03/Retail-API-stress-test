# setup_minikube.ps1
# Automates the setup of Minikube, Docker build, and Kubernetes deployment for the Retail API.

$ErrorActionPreference = "Stop"

# Helper function to run commands synchronously and wait for complete termination with optional timeout
function Run-Command {
    param(
        [string]$Executable,
        [string]$Arguments,
        [int]$TimeoutSeconds = 0
    )
    
    $process = Start-Process -FilePath $Executable -ArgumentList $Arguments -NoNewWindow -PassThru
    
    if ($TimeoutSeconds -gt 0) {
        $process | Wait-Process -Timeout $TimeoutSeconds -ErrorAction SilentlyContinue
        if (-not $process.HasExited) {
            $process | Stop-Process -Force
            throw "$Executable $Arguments timed out after $TimeoutSeconds seconds"
        }
    }
    else {
        $process | Wait-Process
    }
    
    if ($process.ExitCode -ne 0) {
        throw "$Executable $Arguments failed with exit code $($process.ExitCode)"
    }
}

Write-Host "1. Starting Minikube..." -ForegroundColor Cyan
Run-Command -Executable "minikube" -Arguments "start --cpus=6 --memory=8192 --driver=docker"

Write-Host "2. Pointing Docker CLI to Minikube's Docker daemon..." -ForegroundColor Cyan
# This must be run in the current session so environment variables are applied correctly
& minikube -p minikube docker-env --shell powershell | Invoke-Expression

Write-Host "3. Building the Docker image directly inside Minikube's daemon..." -ForegroundColor Cyan
Run-Command -Executable "docker" -Arguments "build -t retail-api:latest ."

Write-Host "4. Enabling the Ingress addon in Minikube..." -ForegroundColor Cyan
Run-Command -Executable "minikube" -Arguments "addons enable ingress" -TimeoutSeconds 60

Write-Host "Waiting for the Ingress Controller to be ready..." -ForegroundColor Cyan
Run-Command -Executable "kubectl" -Arguments "rollout status deployment/ingress-nginx-controller -n ingress-nginx" -TimeoutSeconds 120

Write-Host "5. Creating the namespace 'retail'..." -ForegroundColor Cyan
try {
    Run-Command -Executable "kubectl" -Arguments "create namespace retail"
}
catch {
    Write-Host "Namespace 'retail' already exists or could not be created." -ForegroundColor Yellow
}

Write-Host "6. Deploying postgres database, api, and ingress to 'retail' namespace..." -ForegroundColor Cyan
Run-Command -Executable "kubectl" -Arguments "apply -f k8s/postgres.yaml -n retail"
Run-Command -Executable "kubectl" -Arguments "apply -f k8s/api.yaml -n retail"

# Retry loop for applying ingress.yaml due to transient validation webhook ready delays
$maxRetries = 12
$retryCount = 0
$success = $false
while (-not $success -and $retryCount -lt $maxRetries) {
    try {
        Run-Command -Executable "kubectl" -Arguments "apply -f k8s/ingress.yaml -n retail"
        $success = $true
    }
    catch {
        $retryCount++
        if ($retryCount -lt $maxRetries) {
            Write-Host "Ingress validation webhook not ready yet. Retrying in 5 seconds... ($retryCount/$maxRetries)" -ForegroundColor Yellow
            Start-Sleep -Seconds 5
        }
        else {
            throw "Failed to apply ingress.yaml after $maxRetries retries."
        }
    }
}

Write-Host "Waiting 80 seconds before checking rollout status..." -ForegroundColor Cyan
Start-Sleep -Seconds 80

Write-Host "7. Waiting for the API deployment to be fully ready..." -ForegroundColor Cyan
Run-Command -Executable "kubectl" -Arguments "rollout status deployment/retail-api -n retail" -TimeoutSeconds 30

Write-Host "8. Running setup and seeding scripts inside the active API pod..." -ForegroundColor Cyan
$pod = kubectl get pods -n retail -l app=retail-api -o jsonpath="{.items[0].metadata.name}"

if (-not $pod) {
    Write-Error "No running retail-api pod found in the 'retail' namespace!"
    Exit 1
}

Write-Host "Executing create_admin.py inside pod: $pod" -ForegroundColor Green
Run-Command -Executable "kubectl" -Arguments "exec $pod -n retail -- python create_admin.py"

Write-Host "Executing seed_items.py inside pod: $pod" -ForegroundColor Green
Run-Command -Executable "kubectl" -Arguments "exec $pod -n retail -- python seed_items.py"

Write-Host "All tasks completed successfully!" -ForegroundColor Green


