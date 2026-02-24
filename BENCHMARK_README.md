# VeriTree-GAKE Benchmarks

## Latency (`latency_benchmark.py`)

- **What:** End-to-end protocol execution time (session start → unanimous confirmation).
- **Run:** `python latency_benchmark.py`
- **Output:** LaTeX table (tab:latency), TikZ coordinates (fig:latency), `latency_results.csv`.

## Branching factor (`branching_factor_benchmark.py`)

- **What:** Depth \(h = \lceil \log_b n \rceil\) and per-parent load \(C_{\text{node}}(b) = m \cdot (|ct_{\text{mKEM}}| + b \cdot |ct|)\) for \(n = 64\), \(m = 2\).
- **Run:**
  - `python branching_factor_benchmark.py --reference` — use NIST Kyber512 \(|ct| = 768\) B for the paper table.
  - `python branching_factor_benchmark.py` — use measured \(|ct|\) from the installed KEM (test vectors).
- **Output:** LaTeX table (tab:branching). With `--reference`, per-parent load (KB) is ≈ 5.0, 8.0, 14, 26 for \(b = 2, 4, 8, 16\).

## Paper constants (branching table)

- \(|ct| \approx 800\) bytes in text → use **768** (Kyber512 NIST) for the formula.
- \(|ct_{\text{mKEM}}| \approx 1.3\,|ct| \approx 998\) bytes.
- \(C_{\text{node}}(b) = 2 \cdot (998 + 768b)\) bytes → divide by 1024 for KB.

## Observation paragraph (real values)

- **Latency:** From `latency_benchmark.py`: e.g. n=64 ≈ 29 ms, n=128 ≈ 48 ms (well below 500 ms).
- **Branching:** For \(n \leq 128\), \(b \in [4, 8]\) gives depth 2–3 and per-parent load ≈ 8–14 KB (Table~\ref{tab:branching}).
