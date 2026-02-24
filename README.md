# VeriTree-GAKE Chat Application

Secure group chat application built on **VeriTree-GAKE** (Verifiable Tree Group Authenticated Key Exchange), a post-quantum group key exchange protocol with multi-recipient KEM distribution and split-key hybridization.

## Contents

- **Application code** — FastAPI + WebSockets chat app using VeriTree-GAKE for group key establishment (`app.py`, `config.py`, `models.py`, `crud.py`, `database.py`, `email_service.py`, etc.).
- **Test vectors** — Byte-exact vectors and verification scripts for the protocol. See **[test_vectors/README.md](test_vectors/README.md)** and **[test_vectors/TEST_VECTOR_CHECKLIST.md](test_vectors/TEST_VECTOR_CHECKLIST.md)**.
- **Benchmarks** — Latency and branching-factor benchmarks. See **[BENCHMARK_README.md](BENCHMARK_README.md)**.

## Quick start

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure** — Set `DATABASE_URL`, optional SMTP and `APP_BASE_URL` in `config.py` or environment.

3. **Initialize DB**
   ```bash
   python __init__db.py
   ```

4. **Run the app**
   ```bash
   uvicorn app:app --host 0.0.0.0 --port 8000
   ```

## Test vectors

- **Generate vectors:** `python test_vectors/generate_all.py`
- **Run all verifications:** `python scripts/run_all_verifications.py`

Individual scripts: `scripts/verify_*.py`, `scripts/reproduce_bandwidth.py`, `scripts/reproduce_latency.py`. See **test_vectors/README.md** for the full list and how each vector is used.

## Benchmarks

- **Latency:** `python latency_benchmark.py` (writes `latency_results.csv`)
- **Branching factor:** `python branching_factor_benchmark.py [--reference]`

See **BENCHMARK_README.md** for details.

## License

See repository or project license file.
