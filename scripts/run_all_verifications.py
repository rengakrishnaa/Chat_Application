"""
Run all test-vector verification scripts and report pass/fail.
"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

SCRIPTS = [
    "verify_kem.py",
    "verify_fairness.py",
    "verify_combiner.py",
    "verify_cbor.py",
    "verify_derivation.py",
    "verify_aggregation.py",
    "verify_confirmation.py",
    "verify_transcript.py",
    "verify_exact_reproduction.py",
]
REPRO = ["reproduce_bandwidth.py", "reproduce_latency.py"]


def main():
    failed = []
    for name in SCRIPTS:
        path = os.path.join(os.path.dirname(__file__), name)
        r = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            failed.append(name)
            print(f"FAIL {name}")
            if r.stderr:
                print(r.stderr[:500])
        else:
            print(f"OK   {name}")
    for name in REPRO:
        path = os.path.join(os.path.dirname(__file__), name)
        r = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            failed.append(name)
            print(f"FAIL {name}")
        else:
            print(f"OK   {name} (repro)")
    if failed:
        print("\nFailed:", failed)
        sys.exit(1)
    print("\nAll verifications passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
