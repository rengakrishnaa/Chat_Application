"""
Reproduce latency measurements. Uses the same harness as latency_benchmark.py;
reports total execution time per group size. Phase breakdown (commit_ms, barrier_ms,
reveal_ms) would require an instrumented simulator; see latency_benchmark.py and
Section VII-H.
"""

import io
import sys
import os
import time
import platform

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def run_once(n: int) -> float:
    from veritree_gake.core import VeriTreeSimulator
    n_mod = n - 1
    members_per = 0
    sim = VeriTreeSimulator()
    old = sys.stdout
    sys.stdout = io.StringIO()
    t0 = time.perf_counter()
    sim.run_demo_tree("admin", n_mod, members_per, sid=b"latency-repro")
    t1 = time.perf_counter()
    sys.stdout = old
    return (t1 - t0) * 1000.0


def main():
    print("Latency reproduction (end-to-end protocol execution time)")
    print("Hardware: ", platform.processor() or "N/A", "| Python:", platform.python_version())
    print()
    group_sizes = [8, 16, 32, 64, 128]
    print("  n    |  Time (ms)")
    print("-------+------------")
    for n in group_sizes:
        ms = run_once(n)
        print(f"  {n:3d}  |  {ms:.2f}")
    print()
    print("Phase breakdown (commit / barrier / reveal) requires instrumented")
    print("simulator; see latency_benchmark.py for full harness and Section VII-H.")
    return 0


if __name__ == "__main__":
    main()
