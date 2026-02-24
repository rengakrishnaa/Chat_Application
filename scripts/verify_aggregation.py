"""
Verify level aggregation: B_ℓ = XOR of all node tildeK at level ℓ.
Claims: Level aggregation correctness.
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VECTORS = os.path.join(ROOT, "test_vectors", "aggregation_vectors.json")


def main():
    with open(VECTORS) as f:
        data = json.load(f)
    for level_blob in data.get("levels", []):
        level = level_blob["level"]
        contribs = level_blob["node_contributions_hex"]
        B_level = level_blob["B_level_hex"]
        xor_val = bytes(32)
        for c in contribs:
            b = bytes.fromhex(c)
            xor_val = bytes(a ^ b for a, b in zip(xor_val, b))
        for fam, B_hex in B_level.items():
            if xor_val.hex() != B_hex:
                print(f"  FAIL level {level} family {fam}: XOR of contributions != B_level")
                sys.exit(1)
        print(f"  OK level {level}: B_level = XOR(contributions)")
    print("Aggregation verification passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
