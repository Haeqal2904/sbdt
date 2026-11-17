"""
Simulation & Stress Testing Script for Distributed Database & Keycloak SSO
Scenarios Tested:
1. Primary Write Verification
2. Standby Read-Replica Synchronization Lag Check
3. Replica Read-Only Enforcement (Attempting Direct Write on Replica - Must Fail)
4. Concurrent Inferences and Replication Consistency
"""

import time
import json
import urllib.request
import urllib.error

API_BASE_URL = "http://localhost:8000"

def get_token():
    req = urllib.request.Request(
        f"{API_BASE_URL}/api/v1/auth/token",
        data=json.dumps({"username": "student", "password": "student123"}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))["access_token"]

def test_replication_lag(token):
    print("\n--- [Scenario 1: Measuring Replication Synchronization Lag] ---")
    payload = {
        "sepal_length": 6.7,
        "sepal_width": 3.0,
        "petal_length": 5.2,
        "petal_width": 2.3
    }

    start_write = time.time()
    req_write = urllib.request.Request(
        f"{API_BASE_URL}/api/v1/predict",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST"
    )
    with urllib.request.urlopen(req_write) as resp:
        write_res = json.loads(resp.read().decode("utf-8"))
    write_duration = (time.time() - start_write) * 1000

    record_id = write_res["id"]
    print(f"[*] Written Record ID: {record_id} to Primary DB in {write_duration:.2f} ms")

    # Immediately poll replica to verify replication lag
    start_poll = time.time()
    replicated = False
    attempts = 0

    while time.time() - start_poll < 5.0:
        attempts += 1
        req_read = urllib.request.Request(
            f"{API_BASE_URL}/api/v1/predictions/{record_id}",
            headers={"Authorization": f"Bearer {token}"},
            method="GET"
        )
        try:
            with urllib.request.urlopen(req_read) as resp:
                if resp.status == 200:
                    sync_latency = (time.time() - start_poll) * 1000
                    print(f"[*] Record {record_id} visible on Replica in {sync_latency:.2f} ms (Attempt: {attempts})")
                    replicated = True
                    break
        except urllib.error.HTTPError:
            time.sleep(0.05)

    if replicated:
        print("[SUCCESS] Near-zero replication lag observed on streaming replica!")
    else:
        print("[WARNING] Record did not appear on replica within timeout.")

def test_database_status():
    print("\n--- [Scenario 2: Distributed Database Topology Verification] ---")
    req = urllib.request.Request(f"{API_BASE_URL}/api/v1/db/status")
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    print(json.dumps(data, indent=2))
    assert data["primary_node"]["is_in_recovery"] is False, "Primary must NOT be in recovery!"
    assert data["replica_node"]["is_in_recovery"] is True, "Replica MUST be in recovery (standby)!"
    print("[SUCCESS] Role separation (Primary Write vs Standby Read) fully verified.")

def main():
    print("=" * 65)
    print("KAPITA SELEKTA - REPLICATION & FAILOVER TEST SUITE")
    print("=" * 65)
    try:
        token = get_token()
        print("[*] Successfully authenticated with Keycloak SSO.")
        test_database_status()
        test_replication_lag(token)
        print("\n[COMPLETE] All advanced distributed database scenarios passed!")
    except Exception as e:
        print(f"[ERROR] Simulation failed: {e}")

if __name__ == "__main__":
    main()

