"""
VeriTree-GAKE End-to-End Latency Benchmark

Measures total protocol execution time from session initiation to unanimous
confirmation tag verification, including:
  - Downlink mKEM broadcasts
  - Uplink KEM encapsulations
  - HKDF derivations
  - Dual-commit fairness phase
  - Split-key combiner execution
  - Confirmation tag exchange

Outputs values for Table (tab:latency) and Figure (fig:latency) in the paper.
Run: python latency_benchmark.py
"""

import time
import sys
import io
from typing import List, Tuple

# Suppress verbose logging during benchmark
import logging
logging.getLogger("veritree_gake").setLevel(logging.WARNING)
logging.getLogger("veritree_gake.core").setLevel(logging.WARNING)

from veritree_gake import VeriTreeManager


def group_size_to_params(n: int) -> Tuple[int, int]:
    """
    VeriTree tree: 1 admin + n_mod moderators + (n_mod * members_per_mod) members.
    Total nodes n = 1 + n_mod + n_mod * members_per_mod = 1 + n_mod * (1 + members_per_mod).
    Use n_mod = n - 1, members_per_mod = 0 to get exact n.
    """
    n_mod = n - 1
    members_per_mod = 0
    return n_mod, members_per_mod


def run_protocol_once(n: int, mgr: VeriTreeManager) -> float:
    """Run full VeriTree-GAKE once for group size n; return elapsed time in milliseconds."""
    n_mod, members_per = group_size_to_params(n)
    moderators = [f"mod{i+1}" for i in range(n_mod)]

    # Redirect stdout so benchmark output is clean (protocol may print)
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()

    try:
        t0 = time.perf_counter()
        mgr.create_org_tree(
            "admin",
            moderators,
            members_per_mod=members_per,
            sid=b"latency-bench-2026",
        )
        t1 = time.perf_counter()
        return (t1 - t0) * 1000.0  # ms
    finally:
        sys.stdout = old_stdout


def main():
    group_sizes = [8, 16, 32, 64, 128]
    num_trials = 10
    warmup_runs = 2

    print("=" * 60)
    print("VeriTree-GAKE End-to-End Latency Benchmark")
    print("=" * 60)
    print(f"Group sizes: n = {group_sizes}")
    print(f"Trials per size: {num_trials} (warmup: {warmup_runs})")
    print()

    mgr = VeriTreeManager()

    # Warmup
    print("Warmup...")
    for _ in range(warmup_runs):
        run_protocol_once(8, mgr)
    print("Warmup done.\n")

    results: List[Tuple[int, float, float]] = []  # (n, mean_ms, std_ms)

    for n in group_sizes:
        times_ms = []
        for trial in range(num_trials):
            elapsed = run_protocol_once(n, mgr)
            times_ms.append(elapsed)

        mean_ms = sum(times_ms) / len(times_ms)
        variance = sum((t - mean_ms) ** 2 for t in times_ms) / len(times_ms)
        std_ms = variance ** 0.5
        results.append((n, mean_ms, std_ms))
        print(f"  n = {n:3d}  |  mean = {mean_ms:8.2f} ms  |  std = {std_ms:5.2f} ms  |  min = {min(times_ms):.2f}  max = {max(times_ms):.2f}")

    # Summary table (for paper)
    print()
    print("=" * 60)
    print("LATEX TABLE (copy into Table ~\\ref{tab:latency})")
    print("=" * 60)
    print()
    print(r"\begin{tabular}{|c|c|}")
    print(r"\hline")
    print(r"Group Size $n$ & Execution Time (ms) \\")
    print(r"\hline")
    for n, mean_ms, _ in results:
        # Report rounded mean; use 0 decimal if large, else 1
        if mean_ms >= 100:
            val = f"{round(mean_ms):d}"
        else:
            val = f"{mean_ms:.1f}"
        print(f"  {n}   & {val} \\\\")
    print(r"\hline")
    print(r"\end{tabular}")
    print()

    # TikZ figure coordinates (for fig:latency)
    print("=" * 60)
    print("LATEX FIGURE COORDINATES (for \\addplot in fig:latency)")
    print("=" * 60)
    print()
    coord_str = "coordinates {\n"
    for n, mean_ms, _ in results:
        coord_str += f"    ({n},{mean_ms:.2f})\n"
    coord_str += "};"
    print(coord_str)
    print()

    # CSV for external plotting
    csv_path = "latency_results.csv"
    with open(csv_path, "w") as f:
        f.write("n,mean_ms,std_ms\n")
        for n, mean_ms, std_ms in results:
            f.write(f"{n},{mean_ms:.4f},{std_ms:.4f}\n")
    print(f"Results saved to {csv_path}")

    # Observation note
    print()
    print("Note: Latency includes all protocol phases (mKEM, uplink KEM, HKDF,")
    print("      dual-commit, split-key combiner, confirmation). Core uses a 10 ms")
    print("      barrier in Phase 4–5; subtract ~10 ms if reporting crypto-only time.")
    print()


if __name__ == "__main__":
    main()
