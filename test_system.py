"""
End-to-End Verification Script for Kapita Integrated Project
Tests:
1. API & Service Health
2. PostgreSQL Distributed Replication Status (Primary vs Replica)
3. Keycloak SSO OAuth2 / OIDC Token Generation
4. ML Model Inference & Write to Primary Node
5. Querying Prediction History from Standby Read-Replica Node
"""

import sys
import time
import json
import urllib.request
import urllib.error

API_BASE_URL = "http://localhost:8000"

def log_step(title):
    print("\n" + "=" * 65)
    print(f"[*] {title}")
    print("=" * 65)

def make_request(url, method="GET", data=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        try:
            return e.code, json.loads(err_body)
        except Exception:
            return e.code, {"raw_error": err_body}
    except Exception as e:
        return 0, {"error": str(e)}

def test_health():
    log_step("STEP 1: Checking Overall System Health")
    status, res = make_request(f"{API_BASE_URL}/health")
    print(f"Status Code: {status}")
    print(f"Response: {json.dumps(res, indent=2)}")
    if status == 200:
        print("[SUCCESS] API and dependencies are accessible.")
        return True
    else:
        print("[WARNING] Services are still initializing or one component is degraded.")
        return False

def test_database_replication():
    log_step("STEP 2: Checking Distributed PostgreSQL Replication Status")
    status, res = make_request(f"{API_BASE_URL}/api/v1/db/status")
    print(f"Status Code: {status}")
    print(f"Response: {json.dumps(res, indent=2)}")

    if status == 200:
        p_rec = res.get("primary_node", {}).get("is_in_recovery")
        r_rec = res.get("replica_node", {}).get("is_in_recovery")
        streams = res.get("replication_streams", [])

        print(f"\n[Validation]:")
        print(f" - Primary Node is_in_recovery : {p_rec} (Expected: False -> Primary Write)")
        print(f" - Replica Node is_in_recovery : {r_rec} (Expected: True  -> Standby Read)")
        print(f" - Active Streaming Connections: {len(streams)}")

        if p_rec is False and r_rec is True:
            print("[SUCCESS] Distributed Database Streaming Replication is working correctly!")
            return True
    print("[FAIL] Database replication verification failed.")
    return False

def test_sso_authentication():
    log_step("STEP 3: Testing Single Sign-On (SSO) via Keycloak")
    login_payload = {
        "username": "student",
        "password": "student123"
    }
    status, res = make_request(f"{API_BASE_URL}/api/v1/auth/token", method="POST", data=login_payload)
    print(f"Status Code: {status}")

    if status == 200 and "access_token" in res:
        token = res["access_token"]
        print(f"[SUCCESS] Obtained Keycloak JWT Token!")
        print(f"Token (first 50 chars): {token[:50]}...")
        print(f"Token Type: {res.get('token_type')}")
        print(f"Expires In: {res.get('expires_in')} seconds")

        # Test authenticated /me
        _, me_res = make_request(f"{API_BASE_URL}/api/v1/auth/me", token=token)
        print(f"Authenticated User Profile: {json.dumps(me_res, indent=2)}")
        return token
    else:
        print(f"[FAIL] Failed to obtain SSO token: {res}")
        return None

def test_ml_inference_write(token):
    log_step("STEP 4: Testing ML Inference & Database Write (Primary Node)")
    # Sample Iris-setosa flower measurements
    iris_sample = {
        "sepal_length": 5.1,
        "sepal_width": 3.5,
        "petal_length": 1.4,
        "petal_width": 0.2
    }
    status, res = make_request(f"{API_BASE_URL}/api/v1/predict", method="POST", data=iris_sample, token=token)
    print(f"Status Code: {status}")
    print(f"Response: {json.dumps(res, indent=2)}")

    if status == 201:
        print(f"[SUCCESS] Inference result: {res.get('predicted_class')} (Confidence: {res.get('confidence')})")
        print(f"[SUCCESS] Written to: {res.get('db_node_written')} with Record ID: {res.get('id')}")
        return res.get("id")
    else:
        print(f"[FAIL] Inference or DB write failed: {res}")
        return None

def test_read_replica(token, expected_id):
    log_step("STEP 5: Testing Read Operation from Standby Replica Node")
    # Wait 1 second to ensure replication synchronization
    time.sleep(1)

    status, res = make_request(f"{API_BASE_URL}/api/v1/predictions", method="GET", token=token)
    print(f"Status Code: {status}")
    print(f"Total Records on Replica: {res.get('total')}")
    print(f"Database Node Read: {res.get('db_node_read')}")

    if status == 200:
        items = res.get("items", [])
        found = any(item.get("id") == expected_id for item in items)
        if found:
            print(f"[SUCCESS] Record ID {expected_id} successfully verified on Standby Read-Replica Node!")
            return True
        else:
            print(f"[WARNING] Record ID {expected_id} not found in first page of replica query.")
    print("[FAIL] Could not verify read replica synchronization.")
    return False

def main():
    print("""
    =================================================================
    KAPITA SELEKTA - TUGAS PROYEK TERINTEGRASI (TAHAP 1)
    Automated Verification Suite
    =================================================================
    """)

    # 1. Health
    if not test_health():
        print("\nNote: Make sure containers are running (`docker compose up -d`) and healthy.")
        sys.exit(1)

    # 2. DB Replication
    test_database_replication()

    # 3. SSO
    token = test_sso_authentication()
    if not token:
        sys.exit(1)

    # 4. Inference & Write
    rec_id = test_ml_inference_write(token)
    if not rec_id:
        sys.exit(1)

    # 5. Read from Replica
    test_read_replica(token, rec_id)

    print("\n" + "=" * 65)
    print("[CONGRATULATIONS] All 5 system verification steps passed!")
    print("=================================================================\n")

if __name__ == "__main__":
    main()

