# Event Manager Service
<img width="1370" height="798" alt="image" src="https://github.com/user-attachments/assets/438c7d1d-ac91-47fe-83c0-3f506b1af7f6" />

An independent event wallet, payment, and coupon platform. It supports multiple live events, participant wallet links, vendor PIN access, short-lived payment QR codes, optional participant approval, coupon redemption, immutable audit ledgers, and scheduled bulk actions.

For architecture diagrams, model relationships, common functions, and detailed Windows/Linux development commands, see [`DEVELOPER_GUIDE.md`](DEVELOPER_GUIDE.md).

## NOTICE
```text
I am broke and don't want to pay for an expensive server lmao. So right now the vm option I am using is the weakest vm config possible in Oracle free tier.
```

## Architecture

- **API:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic
- **Web:** Node.js 22, Next.js App Router, TypeScript, Tailwind CSS
- **Database:** MySQL 8.4
- **Runtime:** Docker Compose with separate API, web, database, and scheduler services

Money is stored as integer minor units. Every record is scoped to an event; there is no global current-event state. Participant wallet secrets and session tokens are stored as SHA-256 hashes, passwords and vendor PINs use Argon2id, and PIN lookup uses a keyed HMAC before Argon2 verification.

## Prerequisites

- Docker Desktop on Windows/macOS, or Docker Engine with the Compose plugin on Linux.
- For development outside Docker: Python 3.12, Node.js 22, Corepack, and pnpm.

Verify Docker before starting:

```bash
docker --version
docker compose version
```

On Linux, if Docker requires `sudo`, either prefix the commands below with `sudo` or configure Docker's non-root access for your user.

## Quick start

1. Copy the environment template.

   Windows PowerShell:

   ```powershell
   Copy-Item .env.example .env
   ```

   Linux/macOS:

   ```bash
   cp .env.example .env
   ```

2. Replace `APP_SECRET_KEY` and all database passwords in `.env`. Generate a secret with:

   Windows PowerShell:

   ```powershell
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

   Linux/macOS:

   ```bash
   python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
   ```

3. Start the stack. This command is the same in PowerShell and Linux shells:

   ```bash
   docker compose up --build -d
   docker compose ps
   ```

4. Create the initial administrator without placing the password in shell history:

   ```bash
   docker compose run --rm api python -m app.cli create-admin
   ```

5. Open [http://localhost:3000/admin](http://localhost:3000/admin). Vendors use [http://localhost:3000/wallet](http://localhost:3000/wallet).

Optionally create development-only sample data:

```bash
docker compose run --rm api python -m app.cli seed-demo
```

Useful lifecycle commands on either operating system:

```bash
# Follow service logs
docker compose logs -f api web scheduler

# Stop containers while preserving the MySQL volume
docker compose down

# Rebuild and restart after code changes
docker compose up --build -d
```

### Development mode with automatic reload

Use the development override while actively editing code:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

This bind-mounts the backend and frontend source directories into their containers. FastAPI reloads after Python changes, Next.js applies hot reload after frontend changes, and the scheduler restarts after backend Python changes. You normally do not need to rebuild for source-code edits.

The web container synchronizes its locked dependencies at startup, so after changing `frontend/package.json` or `frontend/pnpm-lock.yaml`, restart `web`. Rebuild after changing `backend/requirements.txt` or a Dockerfile:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

Run detached and follow logs if preferred:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build -d
docker compose -f docker-compose.yml -f docker-compose.dev.yml logs -f api web scheduler
```

Stop the development stack while preserving MySQL data and dependency caches:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml down
```

The normal `docker compose up` command remains the production-style local build and does not enable hot reload.

## Choosing a Docker Compose file

The repository has separate Compose definitions for local development and two different
Oracle deployment layouts. Use only the file or file combination for the intended
environment:

| Environment | Compose files | Environment file | Includes frontend? |
| --- | --- | --- | --- |
| Local, production-style | `docker-compose.yml` | `.env` | Yes |
| Local development with reload | `docker-compose.yml` + `docker-compose.dev.yml` | `.env` | Yes |
| Oracle VM, full stack | `docker-compose.oracle.yml` | `.env.backend` | Yes |
| Oracle VM backend + Vercel frontend | `docker-compose.backend.yml` | `.env.backend` | No |

The Oracle definitions are independent deployments with different Compose project names
and named volumes. Do not switch between them for an existing production database. In
particular, every backend-only production command must include:

```bash
docker compose --env-file .env.backend -f docker-compose.backend.yml ...
```

The backend-only services share `event-manager-backend:latest`. A `git pull` or
`docker compose restart` does not put new source code into existing containers; rebuild the
image, run migrations, and recreate the API and scheduler. See the
[Oracle backend DevOps runbook](event-manager-oracle-devops-commands.md) for deployment,
backup, restore, logging, and recovery commands.

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

### Backend — Windows PowerShell

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
ruff check app tests
mypy app
pytest
```

### Backend — Linux/macOS

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
ruff check app tests
mypy app
pytest
```

### Frontend — Windows, Linux, or macOS

```bash
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

### Oracle Cloud VM deployment

#### Full-stack Oracle deployment

Use `docker-compose.oracle.yml` when the frontend, backend, scheduler, and database all run
on one Oracle VM. It runs
Caddy as the only public service, keeps the API and MySQL on private Docker networks, runs
Alembic as a one-shot migration service, and persists MySQL and Caddy certificate data in
named volumes.

On the VM, clone the repository and create the production environment file:

```bash
cp .env.backend.example .env.backend
chmod 600 .env.backend
```

Replace every placeholder in `.env.backend`. For this full-stack layout,
`CADDY_ADDRESS` is the application hostname and `PUBLIC_APP_URL` is its HTTPS origin. Point
the domain's DNS A record at the VM's
public IP, and allow inbound TCP ports 80 and 443 plus UDP port 443 in both the Oracle Cloud
network security rules and the VM firewall. Do not open ports 3000, 8000, 3306, or 3307.
For a temporary test without a domain, set `CADDY_ADDRESS=http://PUBLIC_IP`, set
`PUBLIC_APP_URL` to the same URL, and set `COOKIE_SECURE=false`. Switch to a domain and HTTPS
before using real participant or vendor credentials.

Build and start the production stack:

```bash
docker compose --env-file .env.backend -f docker-compose.oracle.yml up --build -d
docker compose --env-file .env.backend -f docker-compose.oracle.yml ps
curl --fail-with-body https://events.example.com/health/api
```

Create the initial administrator interactively:

```bash
docker compose --env-file .env.backend -f docker-compose.oracle.yml run --rm api \
  python -m app.cli create-admin
```

For subsequent deployments, pull the desired revision and repeat the `up --build -d`
command. The migration service must finish successfully before the API, scheduler, and web
services start. Back up MySQL separately and regularly; the `mysql-data` volume is persistent
but is not a backup.

#### Backend-only Oracle deployment with Vercel

Use `docker-compose.backend.yml` when Vercel hosts the Next.js frontend and Oracle runs only
MySQL, migrations, FastAPI, the scheduler, and Caddy. Caddy forwards the public backend
hostname directly to FastAPI; this stack does not serve `/admin` or `/wallet` pages.

Create the VM-owned environment file from the committed template, replace every placeholder,
and keep it private:

```bash
cp .env.backend.example .env.backend
chmod 600 .env.backend
```

`CADDY_ADDRESS` is the public backend API hostname, while `PUBLIC_APP_URL` is the separately
deployed Vercel frontend origin. The resulting `.env.backend` is intentionally ignored by
Git. All commands must specify both the environment file and Compose file:

```bash
docker compose --env-file .env.backend -f docker-compose.backend.yml config --quiet
docker compose --env-file .env.backend -f docker-compose.backend.yml ps -a
```

For updates, do not rely on `restart`: the Python code is copied into the backend image at
build time. Follow [section 4 of the production runbook](event-manager-oracle-devops-commands.md#4-routine-safe-deployment)
to build one image at a time, run Alembic, and force-recreate the API and scheduler. Deploy
frontend changes separately through Vercel.
