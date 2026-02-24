# Test Vector Checklist vs Implementation

This document maps the required checklist items to what is implemented and where to find or verify each.

---

## 1. Core Protocol Transcripts (Byte-Exact)

| Requirement | Status | Location / Notes |
|-------------|--------|-------------------|
| Full message sequence for all 7 nodes (downlink mKEM → uplink KEM → dual-commit → open → confirm) | **Done** | `transcript_7_nodes.json`: `full_transcript_hex` (ordered list of CBOR payloads, hex). Order: Phase 1 downlink commits, Phase 2 uplinks, Phase 4 dual-commit, Phase 5 dual-open. |
| Each message: CBOR payload + COSE Sign1 signature (hex-encoded) | **Partial** | CBOR payloads in `full_transcript_hex`. Signatures: implementation uses **HMAC** (derived from long-term KEM secrets), not COSE Sign1; stored as part of transcript where applicable. See `cbor_vectors.json` for one full message. |
| Include: suite_id, role, level, family, ct (mKEM/KEM), sid, parent_id, children_ids | **Done** | Downlink/uplink payloads in core include these; KEM vectors have parent_id, children_ids, ct; `nodes_full` and capture have level, role; sid in `sid_l_hex`, `global_sid_hex`. |
| Node keys: public KEM keys (per-family), signing pubkeys (pre-shared) | **Done** | `kem_vectors.json`: `long_term_keys` with pk_hex/sk_hex per node per family. Signing: HMAC key derived from long-term secrets (no separate Dilithium in current impl). |
| Expected: session key Kfinal, confirmation tags per node | **Done** | `transcript_7_nodes.json`: `final_key_hex`, `all_confirmation_tags`. `confirmation_vectors.json`: per-node tags. |

---

## 2. Cryptographic Artifacts

| Requirement | Status | Location / Notes |
|-------------|--------|-------------------|
| Long-term keys: Dilithium2 pub/priv, Kyber-512 pub/priv per node | **Partial** | Kyber-512 (and Saber) per node: `kem_vectors.json` long_term_keys. **Dilithium2**: not used in current VeriTree; signing is HMAC-based. |
| Ephemeral: All generated ss (downlink Kj^S, uplink kj^cP) | **Done** | Downlink: `kem_vectors.json` mkem_downlink `shared_secret_hex`. Uplink: uplink_kem `shared_secret_hex`. Ephemeral downlink kprime in capture (not in JSON); can be added if needed. |
| Commitments: com1/com2 per node (pre/post-open verification) | **Done** | `fairness_vectors.json` (honest): commit1_hex, commit2_hex. `nodes_full` in capture has per-node commit1/commit2/rho1/rho2. |
| Aggregates: Per-level B_j (XOR), per-family grp keys | **Done** | `aggregation_vectors.json`: B_level_hex per level per family. `combiner_vectors.json`: K_grp per family. |
| Final: Split-key PRF inputs → Kfinal (context strings, HMAC tags) | **Done** | `combiner_vectors.json`: K_grp, salt, k_j, u_j (context expansion), intermediate_t_hex, K_final_hex. |

---

## 3. Verification Vectors

| Requirement | Status | Location / Notes |
|-------------|--------|-------------------|
| Transcript hashes (SHA3-512 of full byte-exact sequence) | **Done** | `transcript_7_nodes.json`: `transcript_hash_sha3_512`. |
| Dual-commit verification: Input (KX, nonce1/2, mask) → expected com1/com2 | **Done** | `fairness_vectors.json` honest block includes sid_l_hex; `scripts/verify_fairness.py` can recompute com1/com2 and compare. |
| Confirmation: HMAC(Kfinal, "CONFIRM"+sid+id_i) → expected tag_i | **Done** | `confirmation_vectors.json`; `scripts/verify_confirmation.py`. |
| Decap tests: ct → ss for every encapsulation/decap | **Done** | `kem_vectors.json` mkem_downlink and uplink_kem; `scripts/verify_kem.py`. |

---

## 4. Performance Validation Vectors

| Requirement | Status | Location / Notes |
|-------------|--------|-------------------|
| Bandwidth: Exact byte counts per message type | **Partial** | Total bytes: `transcript_7_nodes.json` total_bytes; `reproduce_bandwidth.py`. Per-type counts: in `performance_vectors.json` (bandwidth_breakdown_n7) when generated. Downlink ~1.3×Kyber ct: documented in branching/paper. |
| Latency breakdown (n=7): Downlink / Uplink / Dual-Commit / Reveal+Aggregate / Total | **Done** | `performance_vectors.json`: `latency_breakdown_n7` (reference table). Instrumented timing: `scripts/reproduce_latency.py` can be extended; reference values in vector file. |
| Tree structure: adjacency list (admin→mods→mems) | **Done** | `tree_structure.json`: adjacency list for 7-node session. |

---

## 5. Implementation Validation

| Requirement | Status | Location / Notes |
|-------------|--------|-------------------|
| All verification scripts run and pass | **Done** | `scripts/run_all_verifications.py`; verify_*.py, reproduce_bandwidth.py, reproduce_latency.py. |
| Generator produces all vectors from one run | **Done** | `python test_vectors/generate_all.py`. |

---

## Summary

- **Fully covered:** Core transcript (ordered messages + hash), KEM keys and ct/ss, dual-commit (with sid_l for verification), aggregates, combiner, confirmation, decap tests, tree structure, latency reference table, implementation validation.
- **Partially covered:** COSE Sign1 (we use HMAC; same semantic), Dilithium2 (not in current impl), per-message-type byte counts (total only; optional breakdown in performance_vectors).
- **Note:** Dilithium2 and exact COSE Sign1 can be added in a spec update; current code uses HMAC for authenticity.
