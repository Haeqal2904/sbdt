"""
End-to-End Integration Verification Suite for Tahap 3:
Alur Integrasi End-to-End (Data, SSO, & Model)

Tests all 6 steps sequentially against Kubernetes Ingress:
1. Direct SSO authentication to Keycloak to obtain JWT Access Token.
2. Client sends POST request to Backend API with Authorization: Bearer <token>.
3. Backend validates JWT signature using Keycloak's distributed JWKS public keys
   (tested both with valid token and rejected tampered token).
4. Backend executes ML model inference on input payload.
5. Backend stores inference result to Primary Relational Database (Write Routing: pg_is_in_recovery = False).
6. Client queries inference history routed automatically to Read-Replica (Read Routing: pg_is_in_recovery = True),
   proving replication transparency across distinct database nodes.
"""

import base64
import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

AUTH_HOST = "auth.lokal"
API_HOST = "api.lokal"


def log_step(step_num, title):
    print("\n" + "=" * 72)
    print(f"[STEP {step_num}] {title}")
    print("=" * 72)


def resolve_base_url(hostname: str):
    """Uses hostname directly if resolvable, else connects via 127.0.0.1 with Host header."""
    try:
        socket.getaddrinfo(hostname, 80)
        return f"http://{hostname}", None
    except socket.gaierror:
        return "http://127.0.0.1", hostname


def http_json(base_url, host_header, path, method="GET", data=None, form_data=None, headers=None):
    url = f"{base_url}{path}"
    req_headers = dict(headers or {})
    if host_header:
        req_headers["Host"] = host_header

    body = None
    if data is not None:
        req_headers["Content-Type"] = "application/json"
        body = json.dumps(data).encode("utf-8")
    elif form_data is not None:
        req_headers["Content-Type"] = "application/x-www-form-urlencoded"
        body = urllib.parse.urlencode(form_data).encode("utf-8")

    req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"raw_error": raw}
    except urllib.error.URLError as e:
        return 0, {"error": str(e)}


def decode_jwt_header_and_claims(token: str):
    parts = token.split(".")
    def _b64(seg):
        seg += "=" * (-len(seg) % 4)
        return json.loads(base64.urlsafe_b64decode(seg).decode("utf-8"))
    return _b64(parts[0]), _b64(parts[1])


def main():
    print("""
    ========================================================================
    TAHAP 3: END-TO-END INTEGRATION TEST (KEYCLOAK SSO + JWKS + ML + CQRS)
    ========================================================================
    """)

    auth_base, auth_host_hdr = resolve_base_url(AUTH_HOST)
    api_base, api_host_hdr = resolve_base_url(API_HOST)
    pf_proc = None

    # Ensure Ingress port is reachable; fallback to temporary port-forward if port 80 isn't bound
    probe_status, _ = http_json(api_base, api_host_hdr, "/health")
    if probe_status == 0:
        print("[*] Port 80 belum di-forward. Membuka temporary port-forward ke ingress-nginx-controller (18080:80)...")
        pf_proc = subprocess.Popen(
            ["kubectl", "port-forward", "-n", "ingress-nginx", "svc/ingress-nginx-controller", "18080:80"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(2.5)
        auth_base, auth_host_hdr = "http://127.0.0.1:18080", AUTH_HOST
        api_base, api_host_hdr = "http://127.0.0.1:18080", API_HOST

    try:
        # ------------------------------------------------------------------
        # STEP 1: Authenticate directly to Keycloak SSO Server
        # ------------------------------------------------------------------
        log_step(1, "Autentikasi Langsung ke Server SSO (Keycloak) & Ambil JWT Token")
        token_path = "/realms/kapita-realm/protocol/openid-connect/token"
        status, token_res = http_json(
            auth_base,
            auth_host_hdr,
            token_path,
            method="POST",
            form_data={
                "grant_type": "password",
                "client_id": "api-client",
                "client_secret": "api-client-secret-12345",
                "username": "student",
                "password": "student123",
                "scope": "openid profile email",
            },
        )
        if status != 200 or "access_token" not in token_res:
            print(f"[FAIL] Gagal autentikasi ke Keycloak (http://{AUTH_HOST}{token_path}): {status} {token_res}")
            sys.exit(1)

        access_token = token_res["access_token"]
        header, claims = decode_jwt_header_and_claims(access_token)
        print(f" - Keycloak Endpoint : http://{AUTH_HOST}{token_path}")
        print(f" - JWT Algorithm/KID : alg={header.get('alg')}, kid={header.get('kid')}")
        print(f" - Subject / User    : sub={claims.get('sub')}, user={claims.get('preferred_username')}")
        print(f" - Issuer (iss)      : {claims.get('iss')}")
        print("[SUCCESS] JWT Access Token berhasil diperoleh langsung dari Keycloak SSO!")

        # Inspect JWKS Public Key endpoint
        jwks_path = "/realms/kapita-realm/protocol/openid-connect/certs"
        jwks_status, jwks_res = http_json(auth_base, auth_host_hdr, jwks_path)
        matching_kids = [k.get("kid") for k in jwks_res.get("keys", [])]
        print(f" - JWKS Public Endpoint ({jwks_status}): kids={matching_kids}")
        assert header.get("kid") in matching_kids, "Token kid must exist in Keycloak JWKS!"

        # ------------------------------------------------------------------
        # STEP 2 & 3: Negative Security Test (Tampered JWT must be rejected)
        # ------------------------------------------------------------------
        log_step("2 & 3a", "Validasi Keamanan JWKS: Pengujian Penolakan Token Palsu / Tampered")
        tampered_token = access_token[:-10] + "TAMPERED12"
        bad_status, bad_res = http_json(
            api_base,
            api_host_hdr,
            "/api/v1/predict",
            method="POST",
            data={"sepal_length": 5.1, "sepal_width": 3.5, "petal_length": 1.4, "petal_width": 0.2},
            headers={"Authorization": f"Bearer {tampered_token}"},
        )
        print(f" - Request dengan Tampered JWT -> HTTP {bad_status}: {bad_res}")
        if bad_status != 401:
            print(f"[FAIL] Expected 401 Unauthorized for tampered token, got {bad_status}")
            sys.exit(1)
        print("[SUCCESS] Signature token palsu ditolak oleh Backend API melalui verifikasi JWKS!")

        # ------------------------------------------------------------------
        # STEP 2, 3b, 4, 5: Valid POST -> JWKS Verify -> ML Inference -> Primary Write
        # ------------------------------------------------------------------
        log_step("2-5", "POST /api/v1/predict dengan Bearer Token -> JWKS -> Inferensi ML -> Primary DB (Write)")
        sample_payload = {
            "sepal_length": 6.3,
            "sepal_width": 3.3,
            "petal_length": 6.0,
            "petal_width": 2.5,
        }
        pred_status, pred_res = http_json(
            api_base,
            api_host_hdr,
            "/api/v1/predict",
            method="POST",
            data=sample_payload,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        print(f" - HTTP Status        : {pred_status}")
        print(f" - Auth Verification  : {json.dumps(pred_res.get('auth_verification'))}")
        print(f" - ML Inference       : class='{pred_res.get('predicted_class')}', confidence={pred_res.get('confidence')}, model={pred_res.get('model_version')}")
        print(f" - DB Write Routing   : {json.dumps(pred_res.get('db_routing_proof'))}")

        if pred_status != 201:
            print(f"[FAIL] Predict failed: {pred_res}")
            sys.exit(1)

        write_proof = pred_res.get("db_routing_proof") or {}
        assert write_proof.get("is_in_recovery") is False, "Write MUST go to Primary node (is_in_recovery=False)!"
        new_record_id = pred_res["id"]
        primary_ip = write_proof.get("server_ip")
        print(f"[SUCCESS] Record ID={new_record_id} berhasil diinferensi dan ditulis ke Primary Node ({primary_ip})!")

        # ------------------------------------------------------------------
        # STEP 6: Query Riwayat Inferensi -> Read-Replica (Read Routing)
        # ------------------------------------------------------------------
        log_step(6, "GET /api/v1/predictions -> Read Routing ke Standby Read-Replica (Transparansi Replikasi)")
        time.sleep(1.0)
        hist_status, hist_res = http_json(
            api_base,
            api_host_hdr,
            "/api/v1/predictions?limit=10&offset=0",
            method="GET",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        print(f" - HTTP Status        : {hist_status}")
        print(f" - DB Read Routing    : {json.dumps(hist_res.get('db_routing_proof'))}")
        print(f" - Total Records      : {hist_res.get('total')}")

        if hist_status != 200:
            print(f"[FAIL] Read history failed: {hist_res}")
            sys.exit(1)

        read_proof = hist_res.get("db_routing_proof") or {}
        assert read_proof.get("is_in_recovery") is True, "Read MUST go to Replica node (is_in_recovery=True)!"
        replica_ip = read_proof.get("server_ip")

        items = hist_res.get("items", [])
        replicated_item = next((x for x in items if x.get("id") == new_record_id), None)
        assert replicated_item is not None, f"Record ID {new_record_id} not yet replicated to Read-Replica!"

        print(f" - Replicated Record  : id={replicated_item['id']}, class={replicated_item['prediction']}, user={replicated_item['username']}")
        print(f" - Node Separation    : Primary IP={primary_ip} (Write) != Replica IP={replica_ip} (Read)")
        print("[SUCCESS] Transparansi replikasi terbukti: ditulis di Primary, terbaca otomatis dari Read-Replica!")

        print("\n" + "=" * 72)
        print("[ALL PASSED] Seluruh 6 langkah Alur Integrasi End-to-End Tahap 3 berhasil!")
        print("=" * 72 + "\n")
    finally:
        if pf_proc is not None:
            pf_proc.terminate()


if __name__ == "__main__":
    main()
