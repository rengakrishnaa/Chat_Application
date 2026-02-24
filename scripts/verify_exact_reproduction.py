"""
Verify exact reproduction of transcript, session key, and confirmation tags
from the stored 7-node test vectors (byte-exact).

This script does NOT replay the protocol from a fixed seed (the library does not
expose deterministic RNG). It verifies that the stored vectors are internally
consistent: transcript hash matches recomputed hash, K_final is consistent
across transcript/combiner/confirmation, and all 7 confirmation tags verify.
"""

import json
import os
import sys
import hashlib
import hmac

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TV = os.path.join(ROOT, "test_vectors")


def main():
    errors = []

    # 1) Transcript: SHA3-512(full_transcript_hex) == transcript_hash_sha3_512
    with open(os.path.join(TV, "transcript_7_nodes.json")) as f:
        transcript = json.load(f)
    full_hex = transcript.get("full_transcript_hex", [])
    stored_hash = transcript.get("transcript_hash_sha3_512", "")
    if not full_hex or not stored_hash:
        errors.append("transcript_7_nodes.json missing full_transcript_hex or transcript_hash_sha3_512")
    else:
        concat = b"".join(bytes.fromhex(h) for h in full_hex)
        computed = hashlib.sha3_512(concat).hexdigest()
        if computed != stored_hash:
            errors.append("Transcript hash mismatch: recomputed != stored")
        else:
            print("  OK Transcript: SHA3-512(full_transcript_hex) == transcript_hash_sha3_512")

    # 2) Session key K_final consistent across transcript, combiner, confirmation
    k_transcript = transcript.get("final_key_hex", "")
    with open(os.path.join(TV, "combiner_vectors.json")) as f:
        combiner = json.load(f)
    k_combiner = combiner.get("K_final_hex", "")
    with open(os.path.join(TV, "confirmation_vectors.json")) as f:
        conf = json.load(f)
    k_conf = conf.get("K_final_hex", "")

    if not (k_transcript and k_combiner and k_conf):
        errors.append("K_final missing in transcript, combiner, or confirmation vectors")
    elif k_transcript != k_combiner or k_transcript != k_conf:
        errors.append("K_final inconsistent across transcript / combiner / confirmation")
    else:
        print("  OK Session key: K_final identical in transcript, combiner, confirmation")

    # 3) All 7 confirmation tags verify: HMAC(K_final, "CONFIRM"|sid|id_i) == tag_i
    sid_hex = conf.get("sid_hex", "")
    K = bytes.fromhex(k_conf)
    sid = bytes.fromhex(sid_hex)
    tags = transcript.get("all_confirmation_tags", {})
    if len(tags) != 7:
        errors.append("Expected 7 confirmation tags, got %d" % len(tags))
    else:
        for nid, tag_hex in tags.items():
            expected = hmac.new(K, b"CONFIRM|" + sid + b"|" + nid.encode(), "sha256").hexdigest()
            if tag_hex != expected:
                errors.append("Confirmation tag mismatch for node %s" % nid)
                break
        else:
            print("  OK Confirmation: all 7 tags verify against K_final and sid")

    if errors:
        for e in errors:
            print("  FAIL", e)
        sys.exit(1)
    print("\nExact reproduction check passed (transcript hash, K_final, confirmation tags).")
    return 0


if __name__ == "__main__":
    main()
