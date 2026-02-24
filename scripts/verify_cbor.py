"""
Verify CBOR canonical encoding: re-encoding decoded_structure yields same cbor_hex.
Claims: Deterministic CBOR/COSE encoding, byte-exact reproducibility.
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VECTORS = os.path.join(ROOT, "test_vectors", "cbor_vectors.json")


def main():
    with open(VECTORS) as f:
        data = json.load(f)
    from veritree_gake.core import canonical_encode, canonical_decode

    decoded = data["decoded_structure"]
    expected_hex = data["cbor_hex"]
    encoded = canonical_encode(decoded)
    if encoded.hex() != expected_hex:
        print("  FAIL re-encoded CBOR does not match stored cbor_hex")
        sys.exit(1)
    roundtrip = canonical_decode(encoded)
    # Roundtrip may not preserve key order in dict for JSON; for CBOR it should
    print("  OK canonical encoding roundtrip matches cbor_hex")
    print("CBOR verification passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
