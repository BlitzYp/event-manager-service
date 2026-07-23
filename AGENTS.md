# AGENTS.md

This file applies to the entire repository. Keep it concise; use `README.md` for setup and
`DEVELOPER_GUIDE.md` for architecture, domain flows, and detailed troubleshooting.

## Project map

- `backend/`: Python 3.12, FastAPI, SQLAlchemy 2, Alembic, pytest, Ruff, mypy.
- `frontend/`: Node.js 22+, Next.js App Router, React, TypeScript, Vitest, Playwright.
- `docker-compose.yml`: production-style local stack (no source-code reload).
- `docker-compose.dev.yml`: development override with bind mounts and polling reloaders.
- `docker-compose.oracle.yml`: full-stack Oracle VM deployment, including the web service.
- `docker-compose.backend.yml`: production backend-only Oracle deployment; frontend is on Vercel.
- Services: MySQL 8.4, API, scheduler, and web.

## Domain and security invariants

- Scope every persisted record and query to an event; there is no global current event.
- Store money as integer minor units, never floating point.
- Use row locks for balances, QR consumption, payment decisions, and coupon redemption.
- Keep audit history immutable; corrections are adjustments or reversals.
- Treat wallet URLs, session tokens, passwords, PINs, `.env`, and QR payloads as secrets.
- Raw wallet/session tokens are not persisted. Passwords and PINs use Argon2id; PIN lookup
  uses keyed HMAC before verification.
- Email sends create a separate hashed wallet token per delivered participant. Development
  sends remain simulated or test-recipient-limited; managed images require a public HTTPS
  `PUBLIC_APP_URL`, and basic rich-text HTML must stay server-sanitized.
- Scheduled-action run history is audit data. Actions with run history may be disabled or
  edited but must not be deleted.
- Add an Alembic migration for every database schema change.

## Development stack

Plain `docker compose up` uses production images and does **not** auto-reload. For active
development, always use both files for `up`, `logs`, and `down`:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build -d
docker compose -f docker-compose.yml -f docker-compose.dev.yml logs -f api web scheduler
docker compose -f docker-compose.yml -f docker-compose.dev.yml down
```

The development override bind-mounts both source trees. It uses Uvicorn `--reload`,
`watchfiles` for the scheduler, and `next dev --webpack` with polling for WSL/Windows.
Do not use `docker compose down -v` unless the user explicitly wants to delete MySQL data
and dependency/cache volumes.

Local endpoints:

- Web: `http://localhost:3000`
- API: `http://localhost:8000`
- API health through web proxy: `http://localhost:3000/health/api`
- MySQL host port: `3307`

Inside Compose, containers must use service DNS names: the web reaches the API at
`http://api:8000`, not `localhost:8000`. Next.js rewrites and `NEXT_PUBLIC_*` variables are
compiled during `pnpm build`; preserve the web build args in `docker-compose.yml` and the
matching `ARG`/`ENV` declarations in `frontend/Dockerfile`.

The frontend currently has no `public/` directory. Do not add an unconditional Docker
`COPY /app/public` unless that directory is added to the repository.

## Production Compose files

Do not mix the two Oracle deployment definitions. Both use `.env.backend`, but
`docker-compose.oracle.yml` uses project `event-manager-production` while
`docker-compose.backend.yml` uses project `event-manager-backend`; they create different
named volumes. Every Oracle command must include `--env-file .env.backend` and the intended
`-f` argument. Pulling Git changes or restarting containers does not load new backend code:
build the image, run `migrate`, and recreate the Python services. See
`event-manager-oracle-devops-commands.md` for the backend-only safe deployment sequence.
Never commit `.env.backend` or delete a production MySQL volume.

## Validation commands

Run checks relevant to the changed area, expanding to the full suite for cross-cutting work.

Backend (from `backend/`, with the repository virtual environment activated):

```bash
ruff check app tests
mypy app
pytest
```

Frontend (from `frontend/`):

```bash
pnpm install --frozen-lockfile
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

The frontend requires Node 22+. Use Corepack for pnpm; do not install pnpm from Ubuntu
`apt`. `pnpm-workspace.yaml` is a settings file using `allowBuilds`, so pnpm 9 incorrectly
fails with `packages field missing or empty`; use a compatible pnpm 10+ release.

Useful Compose-level checks:

```bash
docker compose ps
curl --fail-with-body http://localhost:3000/health/api
```

## Generated and user-owned files

- `frontend/next-env.d.ts` is maintained by Next.js; do not hand-edit it.
- Regenerate `frontend/src/lib/api.generated.ts` after API contract changes while the API is
  running: `cd frontend && pnpm generate:api`.
- Preserve unrelated working-tree edits. The repository is often used with in-progress
  backend and frontend changes.
