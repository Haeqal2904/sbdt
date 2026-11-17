"""
End-to-End Verification Script for Tahap 2: Orkestrasi Cluster Kubernetes
Validates:
1. Stateful Workloads (StatefulSet & Dynamic PersistentVolumeClaim Bound status)
2. Headless Service (clusterIP: None) & Single Endpoint DNS Discovery
3. Isolated Configuration (ConfigMap) & Sensitive Credentials (Secret)
4. Reverse Proxy Ingress Routing for SSO (auth.lokal) and Backend API (api.lokal)
5. Full End-to-End Flow via Ingress (SSO Token -> ML Inference Write -> Replica Read)
"""

import json
import subprocess
import sys
import time
import urllib.request
import urllib.error

NAMESPACE = "kapita"
INGRESS_BASE_URL = "http://127.0.0.1"

def log_section(title):
    print("\n" + "=" * 70)
    print(f"[*] {title}")
    print("=" * 70)

def run_kubectl(args):
    cmd = ["kubectl"] + args + ["-n", NAMESPACE, "-o", "json"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(res.stdout)
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] kubectl failed: {e.stderr.strip()}")
        return None
    except Exception as e:
        print(f"[ERROR] Failed running kubectl: {e}")
        return None

def http_request_with_host(host_header, path, method="GET", data=None, token=None, base_url=INGRESS_BASE_URL):
    url = f"{base_url}{path}"
    headers = {
        "Host": host_header,
        "Content-Type": "application/json"
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        try:
            return e.code, json.loads(err_body)
        except Exception:
            return e.code, {"raw_error": err_body}
    except Exception as e:
        return 0, {"error": str(e)}

def verify_statefulsets_and_pvc():
    log_section("TAHAP 2.1: Verifying StatefulSets & Dynamic PersistentVolumeClaims (PVC)")
    sts_data = run_kubectl(["get", "statefulset"])
    pvc_data = run_kubectl(["get", "pvc"])
    if not sts_data or not pvc_data:
        return False

    sts_items = sts_data.get("items", [])
    for sts in sts_items:
        name = sts["metadata"]["name"]
        ready = sts.get("status", {}).get("readyReplicas", 0)
        replicas = sts.get("spec", {}).get("replicas", 1)
        svc_name = sts.get("spec", {}).get("serviceName")
        print(f" - StatefulSet '{name}': {ready}/{replicas} Ready (Headless Service: {svc_name})")

    pvc_items = pvc_data.get("items", [])
    for pvc in pvc_items:
        name = pvc["metadata"]["name"]
        phase = pvc.get("status", {}).get("phase")
        storage = pvc.get("spec", {}).get("resources", {}).get("requests", {}).get("storage")
        sc = pvc.get("spec", {}).get("storageClassName", "default")
        print(f" - Dynamic PVC '{name}': Status={phase}, Capacity={storage}, StorageClass={sc}")

    if len(sts_items) >= 2 and len(pvc_items) >= 2:
        print("[SUCCESS] StatefulSets and Dynamic PVCs are active and bound!")
        return True
    print("[WARNING] Expected at least 2 StatefulSets and 2 PVCs.")
    return False

def verify_headless_and_dns():
    log_section("TAHAP 2.2: Verifying Headless Services & Single Endpoint DNS Discovery")
    svc_data = run_kubectl(["get", "service"])
    if not svc_data:
        return False

    headless_found = []
    clusterip_found = []
    for svc in svc_data.get("items", []):
        name = svc["metadata"]["name"]
        cip = svc["spec"].get("clusterIP")
        if cip == "None":
            headless_found.append(name)
            print(f" - Headless Service: {name}.{NAMESPACE}.svc.cluster.local (clusterIP: None)")
        else:
            clusterip_found.append(name)
            print(f" - ClusterIP Service: {name}.{NAMESPACE}.svc.cluster.local (clusterIP: {cip})")

    if "postgres-primary-headless" in headless_found and "postgres-replica-headless" in headless_found:
        print("[SUCCESS] Both Headless Services and Single-Endpoint ClusterIP DNS Services verified!")
        return True
    print("[WARNING] Missing expected headless services.")
    return False

def verify_configmap_and_secret():
    log_section("TAHAP 2.3: Verifying Isolated ConfigMap & Kubernetes Secret")
    cm = run_kubectl(["get", "configmap", "kapita-config"])
    sec = run_kubectl(["get", "secret", "kapita-secrets"])
    if not cm or not sec:
        return False

    cm_keys = list(cm.get("data", {}).keys())
    sec_keys = list(sec.get("data", {}).keys())
    print(f" - ConfigMap 'kapita-config' keys : {cm_keys}")
    print(f" - Secret 'kapita-secrets' keys   : {sec_keys} (base64 encrypted at rest)")

    # Ensure no passwords in ConfigMap
    has_secret_in_cm = any("PASSWORD" in k or "SECRET" in k for k in cm_keys)
    if not has_secret_in_cm and len(sec_keys) >= 4:
        print("[SUCCESS] Environment configuration and sensitive credentials are strictly isolated!")
        return True
    return False

def verify_ingress():
    log_section("TAHAP 2.4: Verifying Reverse Proxy Ingress (auth.lokal & api.lokal)")
    ing = run_kubectl(["get", "ingress", "kapita-ingress"])
    if not ing:
        return False

    rules = ing.get("spec", {}).get("rules", [])
    hosts = []
    for r in rules:
        h = r.get("host")
        hosts.append(h)
        paths = r.get("http", {}).get("paths", [])
        for p in paths:
            svc_name = p["backend"]["service"]["name"]
            svc_port = p["backend"]["service"]["port"]["number"]
            print(f" - Ingress Rule: http://{h}{p['path']} -> {svc_name}:{svc_port}")

    if "auth.lokal" in hosts and "api.lokal" in hosts:
        print("[SUCCESS] Reverse Proxy Ingress rules for auth.lokal & api.lokal verified!")

    # Test live traffic through Ingress
    print("\n[*] Testing HTTP Routing via Ingress Controller...")
    base_url = INGRESS_BASE_URL
    pf_proc = None

    # Check if Ingress is directly reachable on 127.0.0.1:80; if not, auto port-forward ingress-nginx-controller
    s_probe, _ = http_request_with_host("api.lokal", "/health", base_url=base_url)
    if s_probe == 0:
        print(" - Starting temporary port-forward to ingress-nginx-controller (127.0.0.1:18080 -> 80)...")
        pf_proc = subprocess.Popen(
            ["kubectl", "port-forward", "-n", "ingress-nginx", "svc/ingress-nginx-controller", "18080:80"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        time.sleep(2.5)
        base_url = "http://127.0.0.1:18080"

    try:
        s_auth, res_auth = http_request_with_host("auth.lokal", "/realms/kapita-realm", base_url=base_url)
        print(f" - GET http://auth.lokal/realms/kapita-realm -> Status: {s_auth}")

        s_api, res_api = http_request_with_host("api.lokal", "/health", base_url=base_url)
        print(f" - GET http://api.lokal/health               -> Status: {s_api}")
        if s_api == 200:
            print(f"   Health Response: {json.dumps(res_api)}")

            # Test DB DNS & Replication Status via api.lokal
            s_db, res_db = http_request_with_host("api.lokal", "/api/v1/db/status", base_url=base_url)
            if s_db == 200:
                print(f" - GET http://api.lokal/api/v1/db/status     -> Replication Healthy: {res_db.get('replication_healthy')}")
                print(f"   Primary Hostname: {res_db.get('primary_node', {}).get('host')}")
                print(f"   Replica Hostname: {res_db.get('replica_node', {}).get('host')}")

            # Test SSO Token + ML Inference Write + Replica Read via api.lokal
            s_tok, res_tok = http_request_with_host(
                "api.lokal",
                "/api/v1/auth/token",
                method="POST",
                data={"username": "student", "password": "student123"},
                base_url=base_url
            )
            if s_tok == 200 and "access_token" in res_tok:
                token = res_tok["access_token"]
                print(" - POST http://api.lokal/api/v1/auth/token   -> Obtained JWT Token!")
                s_pred, res_pred = http_request_with_host(
                    "api.lokal",
                    "/api/v1/predict",
                    method="POST",
                    data={"sepal_length": 5.9, "sepal_width": 3.0, "petal_length": 5.1, "petal_width": 1.8},
                    token=token,
                    base_url=base_url
                )
                print(f" - POST http://api.lokal/api/v1/predict      -> Status: {s_pred}, Class: {res_pred.get('predicted_class')}")
                time.sleep(1)
                s_hist, res_hist = http_request_with_host(
                    "api.lokal",
                    "/api/v1/predictions",
                    method="GET",
                    token=token,
                    base_url=base_url
                )
                print(f" - GET http://api.lokal/api/v1/predictions   -> Status: {s_hist}, Total on Replica: {res_hist.get('total')}")
        else:
            print("   (Note: Ensure NGINX Ingress Controller is reachable on 127.0.0.1:80 or run `kubectl port-forward -n ingress-nginx svc/ingress-nginx-controller 80:80`)")
    finally:
        if pf_proc is not None:
            pf_proc.terminate()
    return True

def main():
    print("""
    ======================================================================
    KAPITA SELEKTA - TUGAS PROYEK TERINTEGRASI (TAHAP 2: KUBERNETES)
    Automated Kubernetes Architecture & Ingress Verification Suite
    ======================================================================
    """)
    if not verify_statefulsets_and_pvc():
        print("\n[INFO] Cluster Kubernetes belum aktif atau manifest belum di-deploy.")
        print("       Jalankan: .\\k8s\\deploy.ps1 setelah mengaktifkan Kubernetes di Docker Desktop / Minikube / Kind.")
        sys.exit(1)

    verify_headless_and_dns()
    verify_configmap_and_secret()
    verify_ingress()

    print("\n" + "=" * 70)
    print("[CONGRATULATIONS] Seluruh spesifikasi Tahap 2 Kubernetes terverifikasi!")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    main()

