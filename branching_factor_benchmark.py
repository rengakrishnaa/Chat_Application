"""
VeriTree-GAKE Branching Factor Sensitivity Analysis

Computes depth h = ceil(log_b n) and per-parent communication load
C_node(b) = m * (|ct_mKEM| + b*|ct|) for n=64, m=2, using:
  - Measured |ct| from the installed KEM (test vectors), or
  - Reference Kyber512 size (768 bytes) for the paper table.

Output: LaTeX for Table~\ref{tab:branching} and observation text.
Run: python branching_factor_benchmark.py [--reference]
     --reference: use Kyber512 |ct|=768 bytes (NIST) for table values.
"""

import math
import argparse
import sys
import io
import logging

logging.getLogger("veritree_gake").setLevel(logging.WARNING)
logging.getLogger("veritree_gake.core").setLevel(logging.WARNING)

# NIST Kyber512 ciphertext size (round 3)
KYBER512_CT_BYTES = 768
# mKEM compression: single broadcast ct ~ 1.3 * single-recipient ct
MKEM_FACTOR = 1.3


def measure_ct_sizes():
    """Measure |ct| per family from the actual VeriTree KEM (test vectors)."""
    from veritree_gake.core import make_kem_instance
    families = ["Kyber512", "Saber"]
    sizes = {}
    for fam in families:
        try:
            kem = make_kem_instance(fam)
            pk, _ = kem.keygen()
            ctobj, _ = kem.encaps(pk)
            sizes[fam] = len(ctobj["ct"])
        except Exception:
            sizes[fam] = None
    return sizes


def depth_b_ary(n: int, b: int) -> int:
    """Tree depth h = ceil(log_b n) = ceil(log n / log b)."""
    if n <= 1 or b <= 1:
        return 0
    return math.ceil(math.log(n) / math.log(b))


def per_parent_load_kb(m: int, ct_bytes: float, ct_mkem_bytes: float, b: int) -> float:
    """C_node(b) = m * (|ct_mKEM| + b*|ct|) in KB."""
    c_node_bytes = m * (ct_mkem_bytes + b * ct_bytes)
    return c_node_bytes / 1024.0


def main():
    parser = argparse.ArgumentParser(description="Branching factor sensitivity (n=64, m=2)")
    parser.add_argument(
        "--reference",
        action="store_true",
        help="Use Kyber512 |ct|=768 bytes (NIST) for table; otherwise use measured KEM sizes.",
    )
    args = parser.parse_args()

    n = 64
    m = 2  # two KEM families (Kyber512, Saber)

    if args.reference:
        ct_bytes = KYBER512_CT_BYTES
        ct_mkem_bytes = MKEM_FACTOR * ct_bytes
        ct_source = f"Kyber512 reference (NIST): |ct| = {ct_bytes} B, |ct_mKEM| = {ct_mkem_bytes:.0f} B"
    else:
        measured = measure_ct_sizes()
        # Use max across families; if all None use 32 (SimKEM fallback)
        ct_bytes = float(max((v for v in measured.values() if v is not None), default=32))
        ct_mkem_bytes = MKEM_FACTOR * ct_bytes
        ct_source = f"Measured from test vectors: |ct| = {ct_bytes:.0f} B, |ct_mKEM| = {ct_mkem_bytes:.0f} B"

    print("=" * 60)
    print("VeriTree-GAKE Branching Factor Sensitivity (n = 64, m = 2)")
    print("=" * 60)
    print(ct_source)
    print()

    b_values = [2, 4, 8, 16]
    rows = []
    for b in b_values:
        h = depth_b_ary(n, b)
        load_kb = per_parent_load_kb(m, ct_bytes, ct_mkem_bytes, b)
        rows.append((b, h, load_kb))
        print(f"  b = {b:2d}  |  depth h = {h}  |  per-parent load = {load_kb:.2f} KB")

    print()
    print("=" * 60)
    print("LATEX TABLE (copy into Table ~\\ref{tab:branching})")
    print("=" * 60)
    print()
    print(r"\begin{tabular}{|c|c|c|}")
    print(r"\hline")
    print(r"$b$ & Depth $h$ & Per-Parent Load (KB) \\")
    print(r"\hline")
    for b, h, load_kb in rows:
        print(f"  {b} & {h} & $\\approx$ {load_kb:.1f} \\\\")
    print(r"\hline")
    print(r"\end{tabular}")
    print()

    # Optional: one protocol run for n=64 to report total bandwidth (test vector)
    print("=" * 60)
    print("Total bandwidth (n=64) from one protocol run (test vector)")
    print("=" * 60)
    try:
        from veritree_gake import VeriTreeManager
        mgr = VeriTreeManager()
        moderators = [f"mod{i+1}" for i in range(63)]
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        result = mgr.create_org_tree("admin", moderators, members_per_mod=0, sid=b"branch-bench-64")
        sys.stdout = old_stdout
        total_kb = result.get("bandwidth_bytes", 0) / 1024.0
        print(f"  Total protocol bandwidth (n=64): {result.get('bandwidth_bytes', 0)} B ({total_kb:.2f} KB)")
    except Exception as e:
        print(f"  (Run skipped: {e})")
    print()


if __name__ == "__main__":
    main()
