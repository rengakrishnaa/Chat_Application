"""
Verify KEM test vectors: decapsulation reproduces shared secret for downlink and uplink.
Claims: Cryptographic primitive correctness, at-least-one-secure hybrid.
"""

import json
import os
import sys

# Project root
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VECTORS = os.path.join(ROOT, "test_vectors", "kem_vectors.json")


def main():
    with open(VECTORS) as f:
        data = json.load(f)
    from veritree_gake.core import make_kem_instance

    errors = []
    # Verify downlink: parent encapsulated to child; child decaps with sk must get shared_secret
    for vec in data.get("mkem_downlink", []):
        fam = vec["family"]
        kem = make_kem_instance(fam)
        ct_hex = vec.get("ciphertext_hex")
        shared_hex = vec.get("shared_secret_hex")
        if not ct_hex or not shared_hex:
            continue
        # Find child's sk for this family (mod1-mem1)
        sk_hex = None
        for k in data.get("long_term_keys", []):
            if k["family"] == fam and k.get("node_id") == "mod1-mem1":
                sk_hex = k["sk_hex"]
                break
        if not sk_hex:
            errors.append(f"mKEM downlink {fam}: no sk for mod1-mem1")
            continue
        ct = {"ct": bytes.fromhex(ct_hex)}
        if "nonce_hex" in vec:
            ct["nonce"] = bytes.fromhex(vec["nonce_hex"])
        sk = bytes.fromhex(sk_hex)
        try:
            got = kem.decaps(sk, ct)
            expected = bytes.fromhex(shared_hex)
            if got != expected:
                errors.append(f"mKEM downlink {fam}: decaps mismatch")
            else:
                print(f"  OK mKEM downlink {fam}: decaps matches shared secret")
        except Exception as e:
            errors.append(f"mKEM downlink {fam}: {e}")

    for vec in data.get("uplink_kem", []):
        fam = vec["family"]
        kem = make_kem_instance(fam)
        ct_hex = vec.get("ciphertext_hex")
        shared_hex = vec.get("shared_secret_hex")
        if not ct_hex or not shared_hex:
            continue
        # Parent (mod1) decaps
        sk_hex = None
        for k in data.get("long_term_keys", []):
            if k["family"] == fam and k.get("node_id") == "mod1":
                sk_hex = k["sk_hex"]
                break
        if not sk_hex:
            errors.append(f"Uplink {fam}: no sk for mod1")
            continue
        ct = {"ct": bytes.fromhex(ct_hex)}
        if "nonce_hex" in vec:
            ct["nonce"] = bytes.fromhex(vec["nonce_hex"])
        sk = bytes.fromhex(sk_hex)
        try:
            got = kem.decaps(sk, ct)
            expected = bytes.fromhex(shared_hex)
            if got != expected:
                errors.append(f"Uplink {fam}: decaps mismatch")
            else:
                print(f"  OK Uplink {fam}: decaps matches shared secret")
        except Exception as e:
            errors.append(f"Uplink {fam}: {e}")

    if errors:
        for e in errors:
            print("  FAIL", e)
        sys.exit(1)
    print("KEM verification passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
