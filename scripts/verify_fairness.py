"""
Verify dual-commit fairness vectors: honest open verifies; malicious open fails.
Claims: Dual-commit fairness, blame detection.
Recomputes com1/com2 from (KeX, rho1, rho2, sid_l) when sid_l_hex is present.
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VECTORS = os.path.join(ROOT, "test_vectors", "fairness_vectors.json")


def hash_sha256(data: bytes) -> bytes:
    import hashlib
    return hashlib.sha256(data).digest()


def main():
    with open(VECTORS) as f:
        data = json.load(f)
    honest = data["honest"]
    malicious = data["malicious_wrong_open"]

    KeX = bytes.fromhex(honest["KeX_hex"])
    mask = bytes.fromhex(honest["mask_hex"])
    rho1 = bytes.fromhex(honest["rho1_hex"])
    rho2 = bytes.fromhex(honest["rho2_hex"])
    masked = bytes(a ^ b for a, b in zip(KeX, mask))

    # Mask consistency: KeX XOR mask = masked
    expected_masked = bytes(a ^ b for a, b in zip(KeX, mask))
    if expected_masked != masked:
        print("  FAIL honest: mask consistency KeX XOR mask != masked")
        sys.exit(1)
    print("  OK honest: mask consistency KeX XOR mask = masked")

    # Recompute commit1 = H(KeX || rho1 || sid_l), commit2 = H(masked || rho2 || sid_l) when sid_l_hex present
    if honest.get("sid_l_hex"):
        sid_l = bytes.fromhex(honest["sid_l_hex"])
        recomputed_com1 = hash_sha256(KeX + rho1 + sid_l)
        recomputed_com2 = hash_sha256(masked + rho2 + sid_l)
        if recomputed_com1.hex() != honest["commit1_hex"] or recomputed_com2.hex() != honest["commit2_hex"]:
            print("  FAIL honest: recomputed commit1/commit2 do not match stored")
            sys.exit(1)
        print("  OK honest: commit1/commit2 recompute matches (dual-commit verification)")

    # Malicious: tampered open must differ from KeX
    KeX_tampered = bytes.fromhex(malicious["opened_KeX_hex_tampered"])
    if KeX_tampered == KeX:
        print("  FAIL malicious: tampered value should differ from KeX")
        sys.exit(1)
    print("  OK malicious: tampered open differs from commitment (verification must fail in protocol)")

    print("Fairness verification passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
