"""
Verify split-key combiner vectors: recompute K_final from K_grp, salts, u_j, t.
Claims: Split-key hybrid combiner, at-least-one security, domain separation.
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VECTORS = os.path.join(ROOT, "test_vectors", "combiner_vectors.json")


def hash_sha256(data: bytes) -> bytes:
    import hashlib
    return hashlib.sha256(data).digest()


def hmac_sha256(key: bytes, data: bytes) -> bytes:
    import hmac as hm
    import hashlib
    return hm.new(key, data, hashlib.sha256).digest()


def sha3_512(data: bytes) -> bytes:
    import hashlib
    return hashlib.sha3_512(data).digest()


def main():
    with open(VECTORS) as f:
        data = json.load(f)
    K_grp = data["K_grp"]
    k_j = data["k_j"]
    u_j = data["u_j"]
    t_hex = data["intermediate_t_hex"]
    K_final_hex = data["K_final_hex"]
    families_sorted = sorted(K_grp.keys())

    # Recompute k_j from K_grp and salt
    for fam in families_sorted:
        K = bytes.fromhex(K_grp[fam])
        salt_j = hash_sha256(b"salt|" + fam.encode())
        expected_k = hmac_sha256(salt_j, K)
        if expected_k.hex() != k_j[fam]:
            print(f"  FAIL k_j[{fam}] mismatch")
            sys.exit(1)
    print("  OK k_j matches HMAC(salt_j, K_grp)")

    # Recompute t and K_final
    t = bytes([0] * 32)
    for j_idx, family_j in enumerate(families_sorted):
        other_u = b"".join([
            bytes.fromhex(u_j[f]) for f_idx, f in enumerate(families_sorted) if f_idx != j_idx
        ])
        label_j = f"label|{family_j}".encode()
        hmac_val = hmac_sha256(bytes.fromhex(k_j[family_j]), other_u + label_j)
        t = bytes(a ^ b for a, b in zip(t, hmac_val))
    if t.hex() != t_hex:
        print("  FAIL intermediate t mismatch")
        sys.exit(1)
    print("  OK intermediate t matches cross-wire HMAC combination")

    K_final = sha3_512(t)[:32]
    if K_final.hex() != K_final_hex:
        print("  FAIL K_final mismatch")
        sys.exit(1)
    print("  OK K_final = SHA3-512(t)[:32] matches")
    print("Combiner verification passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
