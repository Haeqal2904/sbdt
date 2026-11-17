# PowerShell Deployment Script for Kubernetes (Tahap 2)
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Deploying Kapita Distributed System to Kubernetes Cluster" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

# 1. Build and Tag API Docker Image
Write-Host "`n[1/7] Building API Docker Image..." -ForegroundColor Yellow
docker build -t kapita-api-service:latest -t kapita-api-service:v1.1.0 -f "$ProjectRoot\api\Dockerfile" "$ProjectRoot\api"

# 2. Check / Install NGINX Ingress Controller if not present
Write-Host "`n[2/7] Checking NGINX Ingress Controller..." -ForegroundColor Yellow
$ingressNs = kubectl get ns ingress-nginx --ignore-not-found
if (-not $ingressNs) {
    Write-Host "Installing NGINX Ingress Controller..." -ForegroundColor Yellow
    kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.11.2/deploy/static/provider/cloud/deploy.yaml
    Write-Host "Waiting for Ingress Controller to be ready..." -ForegroundColor Yellow
    kubectl wait --namespace ingress-nginx --for=condition=ready pod --selector=app.kubernetes.io/component=controller --timeout=120s
} else {
    Write-Host "NGINX Ingress Controller is already installed." -ForegroundColor Green
}

# 3. Create Namespace
Write-Host "`n[3/7] Creating Kubernetes Namespace 'kapita'..." -ForegroundColor Yellow
kubectl apply -f "$ScriptDir\00-namespace.yaml"

# 4. Create ConfigMaps and Secrets
Write-Host "`n[4/7] Applying Isolated ConfigMap and Secret..." -ForegroundColor Yellow
kubectl apply -f "$ScriptDir\01-config-secrets.yaml"

# 5. Deploy Distributed PostgreSQL StatefulSets & Headless Services
Write-Host "`n[5/7] Deploying PostgreSQL Primary & Replica StatefulSets + Headless Services..." -ForegroundColor Yellow
kubectl apply -f "$ScriptDir\02-postgres-primary.yaml"
kubectl apply -f "$ScriptDir\03-postgres-replica.yaml"

# 6. Deploy Keycloak SSO and FastAPI Microservice
Write-Host "`n[6/7] Deploying Keycloak SSO and FastAPI Microservice..." -ForegroundColor Yellow
kubectl apply -f "$ScriptDir\04-keycloak.yaml"
kubectl apply -f "$ScriptDir\05-api-service.yaml"

# 7. Deploy Reverse Proxy Ingress (auth.lokal & api.lokal)
Write-Host "`n[7/7] Deploying Reverse Proxy Ingress (auth.lokal & api.lokal)..." -ForegroundColor Yellow
kubectl apply -f "$ScriptDir\06-ingress.yaml"

Write-Host "`n[SUCCESS] All Tahap 2 manifests successfully applied to namespace 'kapita'!" -ForegroundColor Green
Write-Host "Monitor resources with: kubectl get all,pvc,ingress,configmap,secret -n kapita" -ForegroundColor Cyan
Write-Host "Make sure '127.0.0.1 auth.lokal api.lokal' is added to C:\Windows\System32\drivers\etc\hosts" -ForegroundColor Cyan
