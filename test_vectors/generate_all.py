"""
Generate all VeriTree-GAKE test vectors by running the capturing simulator
(7-node session: 1 admin, 2 moderators, 2 members each) and writing
each claim's vectors to a separate JSON file.
"""

import io
import sys
import os
import json
import logging

logging.getLogger("veritree_gake").setLevel(logging.WARNING)
logging.getLogger("veritree_gake.core").setLevel(logging.WARNING)

# Run from project root or test_vectors/
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VECTORS_DIR = SCRIPT_DIR

def main():
    sys.stdout = io.StringIO()
    try:
        from capture_simulator import CapturingSimulator
    except ImportError:
        sys.path.insert(0, SCRIPT_DIR)
        from capture_simulator import CapturingSimulator
    sys.stdout = sys.__stdout__

    sim = CapturingSimulator()
    result = sim.run_demo_tree(
        admin_name="admin",
        n_mod=2,
        members_per=2,
        families=["Kyber512", "Saber"],
        sid=b"test-vector-session-2026",
    )
    cap = sim._capture

    # 1) KEM vectors (per family: keys, one mKEM downlink, one uplink)
    kem = {
        "description": "Cryptographic primitive test vectors per family",
        "families": ["Kyber512", "Saber"],
        "long_term_keys": [],
        "mkem_downlink": [],
        "uplink_kem": [],
    }
    for nid in ["admin", "mod1", "mod1-mem1"]:
        if nid not in cap.get("nodes_keys", {}):
            continue
        for fam, keys in cap["nodes_keys"][nid].items():
            kem["long_term_keys"].append({
                "family": fam,
                "node_id": nid,
                "pk_hex": keys["pk_hex"],
                "sk_hex": keys["sk_hex"],
            })
    if "mod1" in cap["downlinks"] and "mod1-mem1" in cap["downlinks"]["mod1"]:
        for fam in cap["downlinks"]["mod1"]["mod1-mem1"]:
            d = cap["downlinks"]["mod1"]["mod1-mem1"][fam]
            ct = d.get("ct", {})
            mkem_entry = {
                "family": fam,
                "parent_id": "mod1",
                "children_ids": ["mod1-mem1"],
                "ciphertext_hex": ct.get("ct", ""),
                "shared_secret_hex": d.get("k_parent", ""),
            }
            if "nonce" in ct:
                mkem_entry["nonce_hex"] = ct["nonce"]
            kem["mkem_downlink"].append(mkem_entry)
    if "mod1-mem1" in cap.get("uplinks", {}):
        for fam in cap["uplinks"]["mod1-mem1"]:
            u = cap["uplinks"]["mod1-mem1"][fam]
            ct_val = u.get("ct") or {}
            ct_hex = ct_val.get("ct", "") if isinstance(ct_val.get("ct"), str) else (ct_val.get("ct") or b"").hex() if isinstance(ct_val.get("ct"), bytes) else ""
            uplink_entry = {
                "family": fam,
                "child_id": "mod1-mem1",
                "parent_id": "mod1",
                "ciphertext_hex": ct_hex,
                "shared_secret_hex": u.get("k_child", ""),
            }
            if "nonce" in ct_val:
                uplink_entry["nonce_hex"] = ct_val["nonce"] if isinstance(ct_val["nonce"], str) else ct_val["nonce"].hex()
            kem["uplink_kem"].append(uplink_entry)
    with open(os.path.join(VECTORS_DIR, "kem_vectors.json"), "w") as f:
        json.dump(kem, f, indent=2)

    # 2) CBOR canonical encoding (one message)
    from veritree_gake.core import canonical_encode
    sample = {
        "type": "dual_commit",
        "node": "mod1-mem1",
        "level": 0,
        "commit1_hex": cap["dual_commit"]["mod1-mem1"]["commit1_hex"][:64] + "...",
        "commit2_hex": cap["dual_commit"]["mod1-mem1"]["commit2_hex"][:64] + "...",
        "sid_l": cap["sid_l_hex"]["mod1-mem1"],
    }
    cbor_bytes = canonical_encode(sample)
    cbor = {
        "description": "Deterministic CBOR/COSE encoding - byte-exact reproducibility",
        "decoded_structure": sample,
        "cbor_hex": cbor_bytes.hex(),
    }
    with open(os.path.join(VECTORS_DIR, "cbor_vectors.json"), "w") as f:
        json.dump(cbor, f, indent=2)

    # 3) Phase 3 derivation (one node)
    deriv = {
        "description": "Phase 3 per-level secret derivation (HKDF, domain separation)",
        "node_id": "mod1-mem1",
        "sid_hex": cap["sid_l_hex"]["mod1-mem1"],
        "L_j_hex": cap["level_secrets"]["mod1-mem1"],
        "KeX_hex": cap["tildeK"]["mod1-mem1"],
    }
    with open(os.path.join(VECTORS_DIR, "derivation_vectors.json"), "w") as f:
        json.dump(deriv, f, indent=2)

    # 4) Dual-commit fairness (honest + malicious); include sid_l for recomputing com1/com2
    dc = cap["dual_commit"]["mod1-mem1"]
    sid_l_hex = cap.get("sid_l_hex", {}).get("mod1-mem1", "")
    fairness = {
        "description": "Dual-commit fairness: honest open and malicious (commitment mismatch) example",
        "honest": {
            "KeX_hex": dc["KeX_hex"],
            "mask_hex": dc["mask_hex"],
            "rho1_hex": dc["rho1_hex"],
            "rho2_hex": dc["rho2_hex"],
            "sid_l_hex": sid_l_hex,
            "commit1_hex": dc["commit1_hex"],
            "commit2_hex": dc["commit2_hex"],
            "opened_KeX_hex": dc["KeX_hex"],
            "verification_result": True,
        },
        "malicious_wrong_open": {
            "KeX_hex": dc["KeX_hex"],
            "commit1_hex": dc["commit1_hex"],
            "commit2_hex": dc["commit2_hex"],
            "opened_KeX_hex_tampered": (bytes.fromhex(dc["KeX_hex"])[:16] + b"\xff" * 16).hex(),
            "verification_result": False,
            "note": "Opening does not match commitment; verify_dual_open must fail.",
        },
    }
    with open(os.path.join(VECTORS_DIR, "fairness_vectors.json"), "w") as f:
        json.dump(fairness, f, indent=2)

    # 5) Level aggregation
    agg = {
        "description": "Level aggregation B_ℓ = XOR of tildeK at each level",
        "levels": [
            {
                "level": level,
                "families": list(cap["B_per_level"][level].keys()),
                "node_contributions_hex": [
                    cap["nodes_full"][nid]["tildeK"]
                    for nid in sorted(cap["nodes_full"])
                    if cap["nodes_full"][nid]["level"] == level
                ],
                "B_level_hex": {
                    fam: cap["B_per_level"][level][fam]
                    for fam in cap["B_per_level"][level]
                },
            }
            for level in sorted(cap["B_per_level"].keys())
        ],
    }
    with open(os.path.join(VECTORS_DIR, "aggregation_vectors.json"), "w") as f:
        json.dump(agg, f, indent=2)

    # 6) Split-key combiner
    comb = cap["combiner"].copy()
    comb["description"] = "Split-key PRF combiner: at-least-one security, domain separation, cross-wiring"
    with open(os.path.join(VECTORS_DIR, "combiner_vectors.json"), "w") as f:
        json.dump(comb, f, indent=2)

    # 7) Confirmation tags
    conf = {
        "description": "Key confirmation tags per participant",
        "K_final_hex": result["SK_hex"],
        "sid_hex": result["global_sid"],
        "tags": [
            {
                "node_id": nid,
                "confirmation_tag_hex": cap["confirmation_tags"][nid],
                "verified": True,
            }
            for nid in sorted(cap["confirmation_tags"].keys())
        ],
    }
    with open(os.path.join(VECTORS_DIR, "confirmation_vectors.json"), "w") as f:
        json.dump(conf, f, indent=2)

    # 8) Full transcript (7 nodes): ordered message sequence + SHA3-512 hash
    transcript = {
        "description": "Full session transcript - byte-exact reproducibility claim",
        "group_size": 7,
        "branching_factor": 2,
        "full_transcript_hex": cap.get("full_transcript_ordered_hex", []),
        "transcript_hash_sha3_512": cap.get("transcript_hash_sha3_512", ""),
        "final_key_hex": result["SK_hex"],
        "all_confirmation_tags": cap["confirmation_tags"],
        "total_bytes": result["total_bytes"],
        "bandwidth_kb": result["bandwidth_kb"],
    }
    with open(os.path.join(VECTORS_DIR, "transcript_7_nodes.json"), "w") as f:
        json.dump(transcript, f, indent=2)

    # 9) Tree structure (adjacency list)
    tree_structure = {
        "description": "Tree structure: adjacency list for 7-node session (admin -> mods -> mems)",
        "n_nodes": 7,
        "adjacency": {
            "admin": ["mod1", "mod2"],
            "mod1": ["mod1-mem1", "mod1-mem2"],
            "mod2": ["mod2-mem1", "mod2-mem2"],
            "mod1-mem1": [],
            "mod1-mem2": [],
            "mod2-mem1": [],
            "mod2-mem2": [],
        },
    }
    with open(os.path.join(VECTORS_DIR, "tree_structure.json"), "w") as f:
        json.dump(tree_structure, f, indent=2)

    # 10) Performance validation vectors (paper Section VII-H: Phase 4 and 7-node total)
    performance = {
        "description": "Performance validation: latency breakdown (n=7) per paper Section VII-H, bandwidth",
        "latency_breakdown_n7_ms": {
            "Downlink": 18.2,
            "Uplink": 22.1,
            "Phase4_commit_ms": 18,
            "Phase4_barrier_ms": 15,
            "Phase4_reveal_ms": 9,
            "Phase4_total_ms": 42,
            "Reveal_Aggregate": 31.7,
            "Total": 120,
        },
        "bandwidth_n7_bytes": result["total_bytes"],
        "bandwidth_n7_kb": round(result["total_bytes"] / 1024.0, 2),
        "paper_bandwidth_n7_kb": 11.14,
        "paper_bandwidth_kb": {"7": 11.14, "13": 21.63, "31": 53.13, "64": 110.93},
        "paper_latency_ms": {"8": 13.4, "16": 15.2, "32": 19.7, "64": 29.3, "128": 48.0},
        "note": "Total 120 ms and Phase 4 (18+15+9=42 ms) from paper. Bandwidth from this run; paper 11.14 KB at n=7.",
    }
    with open(os.path.join(VECTORS_DIR, "performance_vectors.json"), "w") as f:
        json.dump(performance, f, indent=2)

    print("Generated all test vectors in", VECTORS_DIR)
    print("  kem_vectors.json, cbor_vectors.json, derivation_vectors.json,")
    print("  fairness_vectors.json, aggregation_vectors.json, combiner_vectors.json,")
    print("  confirmation_vectors.json, transcript_7_nodes.json, tree_structure.json,")
    print("  performance_vectors.json")


if __name__ == "__main__":
    main()
