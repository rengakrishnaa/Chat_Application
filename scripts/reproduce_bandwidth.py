"""
Reproduce bandwidth measurements. Runs VeriTree-GAKE for n = 7, 13, 31, 64
and reports total bytes (KB). Paper Section VII-B reports reference values;
actual run may differ unless using deterministic randomness.

calculate_total_bytes(transcript): given a list of message sizes in bytes
(or a list of encoded message bytes), returns total protocol bandwidth in bytes.
For stored transcript use transcript_7_nodes.json "total_bytes" or run the
protocol and use result["total_bytes"].
"""


def calculate_total_bytes(transcript):
    """
    Sum byte lengths from a transcript (list of bytes or list of lengths).
    transcript: list of bytes (each encoded message) or list of int (lengths).
    Returns total bytes.
    """
    total = 0
    for x in transcript:
        if isinstance(x, bytes):
            total += len(x)
        else:
            total += int(x)
    return total

import io
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Paper reference values (Section VII-B)
PAPER_BANDWIDTH_KB = {
    7: 11.14,
    13: 21.63,
    31: 53.13,
    64: 110.93,
}


def run_protocol(n: int) -> int:
    """Run protocol for group size n; return total_bytes (from simulator)."""
    from veritree_gake.core import VeriTreeSimulator
    n_mod = n - 1
    members_per = 0
    sim = VeriTreeSimulator()
    old = sys.stdout
    sys.stdout = io.StringIO()
    result = sim.run_demo_tree("admin", n_mod, members_per, sid=b"bw-bench")
    sys.stdout = old
    return result.get("total_bytes", 0)


def main():
    print("Bandwidth reproduction (total protocol bytes)")
    print("  n   |  Paper (KB)  |  Actual (KB)  |  Actual (bytes)")
    print("------+--------------+---------------+----------------")
    for n in [7, 13, 31, 64]:
        expected_kb = PAPER_BANDWIDTH_KB.get(n)
        total_bytes = run_protocol(n)
        actual_kb = total_bytes / 1024.0
        print(f"  {n:2d}  |  {expected_kb or '—':>10.2f}   |  {actual_kb:>10.2f}   |  {total_bytes}")
    print()
    print("Note: Exact match to paper requires deterministic KEM/randomness.")
    print("Script calculate_total_bytes(transcript) would use stored transcript;")
    print("this script runs the live protocol to show current implementation bandwidth.")
    return 0


if __name__ == "__main__":
    main()
