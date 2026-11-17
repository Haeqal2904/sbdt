#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "=========================================================="
echo "Deploying Kapita Distributed System to Kubernetes Cluster"
echo "=========================================================="

echo "[1/7] Building API Docker Image..."
docker build -t kapita-api-service:latest -t kapita-api-service:v1.1.0 -f "$PROJECT_ROOT/api/Dockerfile" "$PROJECT_ROOT/api"

echo "[2/7] Checking NGINX Ingress Controller..."
if ! kubectl get ns ingress-nginx >/dev/null 2>&1; then
  echo "Installing NGINX Ingress Controller..."
  kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.11.2/deploy/static/provider/cloud/deploy.yaml
  kubectl wait --namespace ingress-nginx --for=condition=ready pod --selector=app.kubernetes.io/component=controller --timeout=120s
fi

echo "[3/7] Creating Kubernetes Namespace..."
kubectl apply -f "$SCRIPT_DIR/00-namespace.yaml"

echo "[4/7] Applying Isolated ConfigMap and Secret..."
kubectl apply -f "$SCRIPT_DIR/01-config-secrets.yaml"

echo "[5/7] Deploying PostgreSQL Primary & Replica StatefulSets + Headless Services..."
kubectl apply -f "$SCRIPT_DIR/02-postgres-primary.yaml"
kubectl apply -f "$SCRIPT_DIR/03-postgres-replica.yaml"

echo "[6/7] Deploying Keycloak SSO and FastAPI Microservice..."
kubectl apply -f "$SCRIPT_DIR/04-keycloak.yaml"
kubectl apply -f "$SCRIPT_DIR/05-api-service.yaml"

echo "[7/7] Deploying Reverse Proxy Ingress (auth.lokal & api.lokal)..."
kubectl apply -f "$SCRIPT_DIR/06-ingress.yaml"

echo "[SUCCESS] All Tahap 2 manifests successfully applied to namespace 'kapita'!"
echo "Monitor resources with: kubectl get all,pvc,ingress,configmap,secret -n kapita"
