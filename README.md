# VeriTree-GAKE Chat Application

Secure group chat application built on **VeriTree-GAKE** (Verifiable Tree Group Authenticated Key Exchange), a post-quantum group key exchange protocol with multi-recipient KEM distribution and split-key hybridization.

The VeriTree-GAKE protocol implementation lives in a separate repository: **[Veri_Tree](https://github.com/rengakrishnaa/Veri_Tree)**. This app depends on it via the `veritree-gake` package (see `requirements.txt`).

---

## Table of contents

- [How to run this project](#how-to-run-this-project)
- [Quick start](#quick-start)
- [Project layout](#project-layout)
- [Configuration](#configuration)
- [Application usage](#application-usage)
- [Test vectors](#test-vectors)
- [Benchmarks](#benchmarks)
- [Pushing to GitHub](#pushing-to-github)
- [License](#license)

---

## How to run this project

### Prerequisites

- **Python 3.9+** (recommended 3.10 or 3.11)
- **PostgreSQL** installed and running (the app uses it for users, groups, and memberships)
- **Git** (needed to install `veritree-gake` from GitHub)

### Step 1: Clone / open the project

```bash
cd d:\Final_Year_Project\Chat_Application\Chat_Application
```

(Or wherever your project folder is.)

### Step 2: Create a virtual environment (recommended)

```bash
python -m venv venv
venv\Scripts\activate
```

On Linux/macOS: `source venv/bin/activate`.

### Step 3: Install dependencies

```bash
pip install -r requirements.txt
```

This installs FastAPI, SQLAlchemy, the VeriTree-GAKE library from GitHub, and the rest. If installation of `veritree-gake` fails, ensure Git is installed and you have network access to `https://github.com/rengakrishnaa/Veri_Tree`.

### Step 4: Set up PostgreSQL

1. Start PostgreSQL and create a database (if it doesn’t exist):

   ```sql
   CREATE DATABASE Secure_chat;
   ```

2. Set the connection string. Either:

   - **Option A — Environment variables** (recommended): create a `.env` file in the project root (or set variables in your shell):

   ```env
   DATABASE_URL=postgresql+psycopg2://postgres:YOUR_PASSWORD@localhost:5432/Secure_chat
   APP_HOST=127.0.0.1
   APP_PORT=8000
   APP_BASE_URL=http://127.0.0.1:8000
   ```

   - **Option B — Edit `config.py`**: change the default `DATABASE_URL` to match your PostgreSQL user, password, host, and database name.

### Step 5: Initialize the database

```bash
python __init__db.py
```

You should see: `Database tables created / updated.`

### Step 6: Run the application

```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```

Or run with the port from config (default 8000):

```bash
python app.py
```

Then open in a browser: **http://localhost:8000**.

### Step 7: Use the app

- **Create Group** tab: create a group with at least one admin; the protocol runs and the group is created.
- **Manage Group** tab: enter the Group ID, load members, add/remove members (triggers rekey).
- **Chat** tab: enter Group ID and your username, click Connect, then send messages.

**Invite links and email:** When you add members (with or without email), the app returns a **join link** for each person. Share that link (e.g. paste in chat or send manually) so they can open it on any device and accept the invite. To **send the link by Gmail** automatically, set `SMTP_USER` and `SMTP_PASSWORD` (and optionally `SMTP_HOST`, `SMTP_PORT`) in `.env` or `config.py`. Set `APP_BASE_URL` to your app’s public URL (e.g. `https://your-domain.com`) so the link in the email works when opened from another device.

### Troubleshooting

| Issue | What to do |
|-------|------------|
| `ModuleNotFoundError: No module named 'veritree_gake'` | Run `pip install -r requirements.txt` again; ensure Git is installed. |
| `connection to server at "localhost" (::1) failed` or `could not connect to server` | Start PostgreSQL and check host/port (default 5432). Verify `DATABASE_URL` in `.env` or `config.py`. |
| `relation "users" does not exist` | Run `python __init__db.py` to create tables. |
| Port already in use | Use another port, e.g. `uvicorn app:app --host 0.0.0.0 --port 8002`, and set `APP_PORT=8002` and `APP_BASE_URL=http://127.0.0.1:8002` so invite links are correct. |

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

   Open **http://localhost:8000** in a browser.

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

If you create a `.env` file in the project root, it is loaded automatically (using `python-dotenv`). Otherwise, set environment variables in your shell or edit the defaults in `config.py`.

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+psycopg2://postgres:postgres@localhost:5432/Secure_chat` |
| `APP_HOST` | Bind host | `127.0.0.1` |
| `APP_PORT` | Bind port | `8000` |
| `APP_BASE_URL` | Base URL for invite links | `http://{APP_HOST}:{APP_PORT}` |
| `SMTP_HOST`, `SMTP_PORT` | SMTP server | Gmail defaults |
| `SMTP_USER`, `SMTP_PASSWORD` | SMTP credentials (optional; if unset, invite emails are skipped) |
| `SMTP_FROM` | From address | Same as `SMTP_USER` |

---

## Application usage

- **Create group** — Tab “Create Group”: name, admins (at least one), moderators, members. Submitting runs VeriTree-GAKE and creates the group; invitation emails are sent if SMTP is configured.
- **Manage group** — Tab “Manage Group”: enter Group ID, load members, add/remove members (triggers rekey). Rekey is also available via API.
- **Chat** — Tab “Chat”: enter Group ID and your **username** (exactly as in the group), then Connect. **Only accepted members** can connect: each member must open the **join link** (from email or shared by you) and accept the invite first. After that they can open the app from any device, enter the same Group ID and username, and chat.

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
