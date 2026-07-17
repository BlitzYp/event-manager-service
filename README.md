# Event Manager Service

An independent event wallet, payment, and coupon platform. It supports multiple live events, participant wallet links, vendor PIN access, short-lived payment QR codes, optional participant approval, coupon redemption, immutable audit ledgers, and scheduled bulk actions.

## Architecture

- **API:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic
- **Web:** Node.js 22, Next.js App Router, TypeScript, Tailwind CSS
- **Database:** MySQL 8.4
- **Runtime:** Docker Compose with separate API, web, database, and scheduler services

Money is stored as integer minor units. Every record is scoped to an event; there is no global current-event state. Participant wallet secrets and session tokens are stored as SHA-256 hashes, passwords and vendor PINs use Argon2id, and PIN lookup uses a keyed HMAC before Argon2 verification.

## Quick start

1. Copy the environment template:

   ```powershell
   Copy-Item .env.example .env
   ```

2. Replace `APP_SECRET_KEY` and all database passwords in `.env`. Generate a secret with:

   ```powershell
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

3. Start the stack:

   ```powershell
   docker compose up --build -d
   ```

4. Create the initial administrator without placing the password in shell history:

   ```powershell
   docker compose run --rm api python -m app.cli create-admin
   ```

5. Open [http://localhost:3000/admin](http://localhost:3000/admin). Vendors use [http://localhost:3000/wallet](http://localhost:3000/wallet).

Optionally run `docker compose run --rm api python -m app.cli seed-demo` to create a development-only event.

## Participant onboarding

Admins can create one participant or import a UTF-8 CSV. The required columns are `participant_code,name`; optional columns are `group,email`.

```csv
participant_code,name,group,email
P-001,Ada Lovelace,Speakers,ada@example.com
P-002,Alan Turing,Guests,alan@example.com
```

The import is all-or-nothing. A successful import downloads a one-time result CSV containing wallet links. Raw wallet tokens are never retained, so a lost link must be rotated from the admin participant list.

## Operational flows

- Participant pages are `/wallet/{secret}`. Money events let participants create a short-lived QR; coupon events expose single-use coupon QR codes.
- Vendors sign in with an event code and event-scoped six-digit PIN. Camera scanning uses the browser scanner with a manual participant-code fallback.
- Approval-enabled payments reserve funds until approved, rejected, or expired. Immediate events settle atomically at creation.
- The scheduler checks every minute, cancels expired pending payments, and runs due one-time or daily bulk actions under a MySQL advisory lock.
- CSV and XLSX transaction exports preserve references, actor snapshots, status, and event ownership.

## Development

Backend:

```powershell
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
ruff check app tests
mypy app
pytest
```

Frontend:

```powershell
cd frontend
corepack enable
pnpm install --frozen-lockfile
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

The OpenAPI document is available at `/api/openapi.json`; generate frontend types while the API is running with `pnpm generate:api`.

## Production requirements

- Put the application behind HTTPS and set `COOKIE_SECURE=true`.
- Use unique high-entropy database and application secrets managed by the deployment platform.
- Do not expose MySQL publicly; the published port is intended only for local development.
- Back up MySQL, test restores, retain audit records, and monitor API/scheduler health and failed vendor logins.
- Run `alembic upgrade head` before each API rollout. The Compose API command does this automatically.

