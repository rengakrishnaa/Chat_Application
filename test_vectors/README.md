# VeriTree-GAKE Test Vectors

This folder contains test vectors that allow **independent verification** of protocol behavior and cryptographic artifacts. The protocol implementation and experiments live in the **[Veri_Tree](https://github.com/rengakrishnaa/Veri_Tree)** repository.

**Checklist:** See **TEST_VECTOR_CHECKLIST.md** for a line-by-line mapping of requirements (core transcripts, cryptographic artifacts, verification vectors, performance, implementation validation) to files and scripts.

## Claims and Corresponding Vectors

| Claim | Vector File(s) | Verification Script |
|-------|----------------|---------------------|
| Deterministic CBOR/COSE encoding | `cbor_vectors.json` | `scripts/verify_cbor.py` |
| Byte-exact transcripts | `transcript_7_nodes.json` | `scripts/verify_transcript.py` |
| Dual-commit fairness | `fairness_vectors.json` | `scripts/verify_fairness.py` |
| Split-key hybrid combiner | `combiner_vectors.json` | `scripts/verify_combiner.py` |
| Bandwidth measurements | (from protocol run) | `scripts/reproduce_bandwidth.py` |
| Latency measurements | (from timing harness) | `scripts/reproduce_latency.py` |
| At-least-one-secure hybrid | KEM + combiner vectors | `scripts/verify_kem.py`, `scripts/verify_combiner.py` |
| Cryptographic primitives (per family) | `kem_vectors.json` | `scripts/verify_kem.py` |
| Phase 3 derivation | `derivation_vectors.json` | `scripts/verify_derivation.py` |
| Level aggregation | `aggregation_vectors.json` | `scripts/verify_aggregation.py` |
| Confirmation tags | `confirmation_vectors.json` | `scripts/verify_confirmation.py` |
| Full transcript (ordered messages + SHA3-512 hash) | `transcript_7_nodes.json` | `scripts/verify_transcript.py` |
| Tree structure (adjacency list) | `tree_structure.json` | — |
| Performance (latency breakdown, bandwidth) | `performance_vectors.json` | `scripts/reproduce_bandwidth.py`, `reproduce_latency.py` |

## Generating Vectors

From the project root:

```bash
python test_vectors/generate_all.py
```

This runs the VeriTree-GAKE protocol (7-node session: 1 admin, 2 moderators, 2 members each), captures all intermediates, and writes the JSON files in this directory.

## Verifying All Claims

From the project root:

```bash
python scripts/verify_kem.py
python scripts/verify_fairness.py
python scripts/verify_combiner.py
python scripts/verify_cbor.py
python scripts/verify_derivation.py
python scripts/verify_aggregation.py
python scripts/verify_confirmation.py
python scripts/verify_transcript.py
python scripts/reproduce_bandwidth.py
python scripts/reproduce_latency.py
```

Or run the test runner:

```bash
python scripts/run_all_verifications.py
```

## Bandwidth and Latency

- **Bandwidth:** `scripts/reproduce_bandwidth.py` runs the protocol for n = 7, 13, 31, 64 and reports total bytes. Reference values (e.g. 11.14 KB at n=7) are in `performance_vectors.json`. `calculate_total_bytes(transcript)` sums message lengths from a transcript.
- **Latency:** `scripts/reproduce_latency.py` reports end-to-end execution time per group size. See `latency_benchmark.py` and `latency_results.csv` for measured latency by n.
