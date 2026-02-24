# VeriTree-GAKE Chat Application

Secure group chat application built on **VeriTree-GAKE** (Verifiable Tree Group Authenticated Key Exchange), a post-quantum group key exchange protocol with multi-recipient KEM distribution and split-key hybridization.

The VeriTree-GAKE protocol implementation lives in a separate repository: **[Veri_Tree](https://github.com/rengakrishnaa/Veri_Tree)**. This app depends on it via the `veritree-gake` package (see `requirements.txt`).

---

## Table of contents

- [Quick start](#quick-start)
- [Project layout](#project-layout)
- [Configuration](#configuration)
- [Application usage](#application-usage)
- [Test vectors](#test-vectors)
- [Benchmarks](#benchmarks)
- [Pushing to GitHub](#pushing-to-github)
- [License](#license)

---

## Quick start

1. **Install dependencies** (includes VeriTree-GAKE from [Veri_Tree](https://github.com/rengakrishnaa/Veri_Tree)):

   ```bash
   pip install -r requirements.txt
   ```

2. **Configure** — Set `DATABASE_URL`, and optionally SMTP and `APP_BASE_URL`, in `config.py` or via environment variables.

3. **Initialize the database:**

   ```bash
   python __init__db.py
   ```

4. **Run the app:**

   ```bash
   uvicorn app:app --host 0.0.0.0 --port 8000
   ```

   Open `http://localhost:8000` in a browser.

---

## Project layout

| Path | Purpose |
|------|--------|
| `app.py` | FastAPI app: REST API, WebSocket chat, embedded UI |
| `config.py` | Settings (DB, SMTP, app URL) from env |
| `models.py` | SQLAlchemy models: User, Group, GroupMembership, GroupTree |
| `crud.py` | DB operations: users, memberships, roles |
| `database.py` | Engine, session, `get_db` |
| `email_service.py` | Invitation emails (SMTP) |
| `__init__db.py` | Creates DB tables |
| `test_vectors/` | Protocol test vectors (JSON) and generator |
| `scripts/` | Verification scripts for test vectors |
| `latency_benchmark.py` | Protocol latency benchmark |
| `branching_factor_benchmark.py` | Branching factor / per-parent load |

---

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+psycopg2://postgres:postgres@localhost:5432/Secure_chat` |
| `APP_HOST` | Bind host | `127.0.0.1` |
| `APP_PORT` | Bind port | `8001` |
| `APP_BASE_URL` | Base URL for invite links | `http://{APP_HOST}:{APP_PORT}` |
| `SMTP_HOST`, `SMTP_PORT` | SMTP server | Gmail defaults |
| `SMTP_USER`, `SMTP_PASSWORD` | SMTP credentials (optional; if unset, invite emails are skipped) |
| `SMTP_FROM` | From address | Same as `SMTP_USER` |

---

## Application usage

- **Create group** — Tab “Create Group”: name, admins (at least one), moderators, members. Submitting runs VeriTree-GAKE and creates the group; invitation emails are sent if SMTP is configured.
- **Manage group** — Tab “Manage Group”: enter Group ID, load members, add/remove members (triggers rekey). Rekey is also available via API.
- **Chat** — Tab “Chat”: enter Group ID and username, connect. Messages are encrypted via the group session and broadcast over WebSocket.

Invitation links use the form `{APP_BASE_URL}/join/{token}`; accepting marks the membership as accepted.

---

## Test vectors

Test vectors allow **independent verification** of protocol behavior and cryptographic artifacts. All vectors are in `test_vectors/`; verification scripts are in `scripts/`.

### Claims and corresponding vectors

| Claim | Vector file(s) | Verification script |
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

### Generate vectors

From the project root:

```bash
python test_vectors/generate_all.py
```

This runs the VeriTree-GAKE protocol (7-node session: 1 admin, 2 moderators, 2 members each), captures intermediates, and writes the JSON files under `test_vectors/`.

### Run all verifications

```bash
python scripts/run_all_verifications.py
```

Individual scripts: `scripts/verify_kem.py`, `scripts/verify_fairness.py`, `scripts/verify_combiner.py`, `scripts/verify_cbor.py`, `scripts/verify_derivation.py`, `scripts/verify_aggregation.py`, `scripts/verify_confirmation.py`, `scripts/verify_transcript.py`, `scripts/reproduce_bandwidth.py`, `scripts/reproduce_latency.py`.

### Checklist summary

Verification covers: core transcript (ordered messages + hash), KEM keys and ct/ss, dual-commit (with sid_l), aggregates, combiner, confirmation, decap tests, tree structure, and performance references. Signing is HMAC-based (not COSE Sign1); Dilithium2 is not used in the current implementation.

---

## Benchmarks

Protocol implementation and experiments: **[Veri_Tree](https://github.com/rengakrishnaa/Veri_Tree)**.

### Latency (`latency_benchmark.py`)

- **What:** End-to-end protocol execution time (session start → unanimous confirmation).
- **Run:** `python latency_benchmark.py`
- **Output:** LaTeX table (tab:latency), TikZ coordinates (fig:latency), `latency_results.csv`.
- **Typical values:** e.g. n=64 ≈ 29 ms, n=128 ≈ 48 ms.

### Branching factor (`branching_factor_benchmark.py`)

- **What:** Depth \(h = \lceil \log_b n \rceil\) and per-parent load \(C_{\text{node}}(b) = m \cdot (|ct_{\text{mKEM}}| + b \cdot |ct|)\) for \(n = 64\), \(m = 2\).
- **Run:**
  - `python branching_factor_benchmark.py --reference` — use NIST Kyber512 \(|ct| = 768\) B for the paper table.
  - `python branching_factor_benchmark.py` — use measured \(|ct|\) from the installed KEM (test vectors).
- **Output:** LaTeX table (tab:branching). With `--reference`, per-parent load (KB) is ≈ 5.0, 8.0, 14, 26 for \(b = 2, 4, 8, 16\).
- **Paper constants:** \(|ct| \approx 768\) B (Kyber512), \(|ct_{\text{mKEM}}| \approx 1.3\,|ct| \approx 998\) B; \(C_{\text{node}}(b) = 2 \cdot (998 + 768b)\) bytes → divide by 1024 for KB.

---

## Pushing to GitHub

1. Create a new repository on [github.com/new](https://github.com/new). Do **not** add a README, .gitignore, or license (this project already has them).
2. From the project folder:

   ```bash
   git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
   git push -u origin main
   ```

   If the remote already exists: `git remote set-url origin ...` then push.

---

## License

See the repository or project license file.
