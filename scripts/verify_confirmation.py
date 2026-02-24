"""
Verify key confirmation tags: τ_i = HMAC(K_final, "CONFIRM" || sid || node_id).
Claims: Key confirmation, unanimity.
"""

import json
import os
import sys
import hmac
import hashlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VECTORS = os.path.join(ROOT, "test_vectors", "confirmation_vectors.json")


def main():
    with open(VECTORS) as f:
        data = json.load(f)
    K_final = bytes.fromhex(data["K_final_hex"])
    sid = bytes.fromhex(data["sid_hex"])
    for tag_entry in data.get("tags", []):
        nid = tag_entry["node_id"]
        expected_tag = tag_entry["confirmation_tag_hex"]
        confirm_input = b"CONFIRM|" + sid + b"|" + nid.encode()
        computed = hmac.new(K_final, confirm_input, hashlib.sha256).hexdigest()
        if computed != expected_tag:
            print(f"  FAIL {nid}: tag mismatch")
            sys.exit(1)
        print(f"  OK {nid}: confirmation tag verifies")
    print("Confirmation verification passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
