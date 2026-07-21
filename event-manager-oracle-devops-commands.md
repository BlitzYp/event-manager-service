# Event Manager Service — Oracle VM DevOps Runbook

Production operations reference for the Event Manager Service.

- Repository: <https://github.com/BlitzYp/event-manager-service>
- Deployment: Vercel frontend and Oracle VM backend
- VM services: Caddy, FastAPI API, scheduler, and MySQL
- Source reference: `event-manager-oracle-devops-commands.txt`
- Last confirmed against commit `9205ff7` (`Fixed bug with disabled events`) on 2026-07-21

> [!IMPORTANT]
> The backend-only `docker-compose.backend.yml` and `.env.backend.example` are committed to
> this repository. The populated `.env.backend` exists only on the Oracle VM and is
> intentionally ignored by Git. The committed `docker-compose.oracle.yml`
> describes a different, full-stack deployment and must not be substituted for
> the backend-only production file.

Reasoning
```text
I am broke and don't want to pay for an expensive server lmao. So right now the vm option I am using is the weakest vm config possible in Oracle free tier. 
```

The production Compose project is named `event-manager-backend`. It uses the
shared image `event-manager-backend:latest`, a one-shot `migrate` service, and
Caddy forwarding directly to `api:8000`.

Every backend-only Compose command must include both:

```text
--env-file .env.backend
-f docker-compose.backend.yml
```

Omitting `--env-file` can produce errors such as `required variable
PUBLIC_APP_URL is missing a value`.

> [!CAUTION]
> Never run `docker compose down -v`, `docker volume prune`, or any command that
> removes the production MySQL volume.

## Contents

1. [Connect to the VM](#1-connect-to-the-vm)
2. [Optional short command](#2-optional-short-command)
3. [Pre-flight checks](#3-pre-flight-checks)
4. [Routine safe deployment](#4-routine-safe-deployment)
5. [Quick deployment](#5-quick-deployment)
6. [Status, logs, and health checks](#6-status-logs-and-health-checks)
7. [Migrations](#7-migrations)
8. [Create or reset a super-admin](#8-create-or-reset-a-super-admin)
9. [Scheduler operations](#9-scheduler-operations)
10. [MySQL console](#10-mysql-console)
11. [MySQL backup](#11-mysql-backup)
12. [MySQL restore](#12-mysql-restore)
13. [Memory, disk, and OOM checks](#13-memory-disk-and-oom-checks)
14. [Restart and recovery](#14-restart-and-recovery)
15. [Safe cleanup](#15-safe-cleanup)
16. [Identify the production database volume](#16-identify-the-production-database-volume)
17. [Recover from using the wrong Compose file](#17-recover-from-using-the-wrong-compose-file)
18. [Change the Vercel public URL](#18-change-the-vercel-public-url)
19. [Protect production deployment files](#19-protect-production-deployment-files)
20. [Day-to-day checklist](#20-day-to-day-checklist)
21. [Commands requiring extra caution](#21-commands-requiring-extra-caution)

## 1. Connect to the VM

From a computer that permits outbound SSH:

```bash
chmod 600 ~/.ssh/ssh-key-oracle.key
ssh -i ~/.ssh/ssh-key-oracle.key ubuntu@92.5.33.108
```

Enter the repository and confirm its state:

```bash
cd ~/event-manager-service
pwd
git status --short
git log -1 --oneline
```

## 2. Optional short command

Define this function after entering the repository directory:

```bash
dc() {
  docker compose --env-file .env.backend -f docker-compose.backend.yml "$@"
}
```

Examples:

```bash
dc ps -a
dc logs --tail=100 api
```

The function exists only in the current shell unless added to a shell profile.
The complete commands remain preferable in scripts and documentation.

## 3. Pre-flight checks

If this is the first deployment, create the production environment file and replace every
placeholder before continuing:

```bash
cp .env.backend.example .env.backend
nano .env.backend
chmod 600 .env.backend
```

For an existing deployment, do not overwrite `.env.backend`. Confirm the required files
exist and protect the secrets file:

```bash
cd ~/event-manager-service
test -f docker-compose.backend.yml
test -f .env.backend
chmod 600 .env.backend
```

Show only non-secret public settings:

```bash
grep -E '^(CADDY_ADDRESS|PUBLIC_APP_URL|COOKIE_SECURE)=' .env.backend
```

Validate environment interpolation and Compose syntax:

```bash
docker compose \
  --env-file .env.backend \
  -f docker-compose.backend.yml \
  config --quiet
```

Check the repository and VM capacity:

```bash
git status --short
df -h /
free -h
docker system df
```

If Git reports unexpected local changes, inspect them before pulling:

```bash
git diff
```

Keep `docker-compose.backend.yml` aligned with Git. Do not overwrite the
VM-owned `.env.backend` during an update.

## 4. Routine safe deployment

This is the recommended deployment sequence for the 1 GB E2 VM. It builds one
backend image, stops only the application processes during migration, and
keeps MySQL running.

### 4.1 Update and validate the source

```bash
cd ~/event-manager-service
git status --short
git pull --ff-only
git log -1 --oneline

docker compose \
  --env-file .env.backend \
  -f docker-compose.backend.yml \
  config --quiet
```

### 4.2 Build the backend image

The `api`, `scheduler`, and `migrate` services share
`event-manager-backend:latest`, so building `api` updates the image used by all
three services.

```bash
COMPOSE_PARALLEL_LIMIT=1 docker compose \
  --env-file .env.backend \
  -f docker-compose.backend.yml \
  build api
```

> [!NOTE]
> Pulling Git changes or running `docker compose restart` does not rebuild the
> image. Containers must be recreated after the build to run the new code.

### 4.3 Stop application processes and migrate

```bash
docker compose \
  --env-file .env.backend \
  -f docker-compose.backend.yml \
  stop api scheduler

docker compose \
  --env-file .env.backend \
  -f docker-compose.backend.yml \
  run --rm migrate
```

### 4.4 Recreate and start services

```bash
docker compose \
  --env-file .env.backend \
  -f docker-compose.backend.yml \
  up -d --no-build --force-recreate api scheduler

docker compose \
  --env-file .env.backend \
  -f docker-compose.backend.yml \
  up -d --no-build --remove-orphans
```

### 4.5 Verify the deployment

```bash
docker compose \
  --env-file .env.backend \
  -f docker-compose.backend.yml \
  ps -a

docker compose \
  --env-file .env.backend \
  -f docker-compose.backend.yml \
  exec api alembic current

docker compose \
  --env-file .env.backend \
  -f docker-compose.backend.yml \
  exec api alembic heads
```

At the recorded source revision, Alembic reports `0003 (head)`. Future commits
may add newer revisions, so compare `current` with `heads` instead of relying on
that value indefinitely.

## 5. Quick deployment

Use this only when Compose-driven migration is acceptable:

```bash
COMPOSE_PARALLEL_LIMIT=1 docker compose \
  --env-file .env.backend \
  -f docker-compose.backend.yml \
  up --build -d --remove-orphans
```

The backend-only file has a one-shot `migrate` service. The API and scheduler
depend on its successful completion. For greater certainty and clearer failure
handling, use the explicit procedure in [Routine safe deployment](#4-routine-safe-deployment).

## 6. Status, logs, and health checks

### Container status

```bash
docker compose \
  --env-file .env.backend \
  -f docker-compose.backend.yml \
  ps -a
```

Expected state:

| Service | Expected state |
| --- | --- |
| `mysql` | Running and healthy |
| `migrate` | Exited with code 0, or absent after `run --rm` |
| `api` | Running and healthy |
| `scheduler` | Running |
| `caddy` | Running |

### Logs

```bash
# Recent logs from all services
docker compose --env-file .env.backend -f docker-compose.backend.yml logs --tail=100

# Follow application logs
docker compose --env-file .env.backend -f docker-compose.backend.yml \
  logs -f --tail=100 api scheduler

# Individual services
docker compose --env-file .env.backend -f docker-compose.backend.yml logs --tail=200 mysql
docker compose --env-file .env.backend -f docker-compose.backend.yml logs --tail=200 migrate
docker compose --env-file .env.backend -f docker-compose.backend.yml logs --tail=200 api
docker compose --env-file .env.backend -f docker-compose.backend.yml logs --tail=200 scheduler
docker compose --env-file .env.backend -f docker-compose.backend.yml logs --tail=200 caddy
```

### Public backend health

Read the backend hostname without displaying secret settings:

```bash
API_HOST="$(sed -n 's/^CADDY_ADDRESS=//p' .env.backend)"
printf '%s\n' "$API_HOST"
curl --fail-with-body --retry 5 --retry-delay 3 "https://${API_HOST}/health"
```

Expected response:

```json
{"status":"ok"}
```

### Vercel proxy health

```bash
VERCEL_URL="https://YOUR-PROJECT.vercel.app"
curl --fail-with-body "${VERCEL_URL}/health/api"
```

### Internal API health

Use this when public HTTPS is the only failing layer:

```bash
docker compose \
  --env-file .env.backend \
  -f docker-compose.backend.yml \
  exec api python -c \
  "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health').read().decode())"
```

## 7. Migrations

Run all pending migrations:

```bash
docker compose --env-file .env.backend -f docker-compose.backend.yml \
  run --rm migrate
```

Inspect migration state while the API is running:

```bash
docker compose --env-file .env.backend -f docker-compose.backend.yml exec api alembic current
docker compose --env-file .env.backend -f docker-compose.backend.yml exec api alembic heads
docker compose --env-file .env.backend -f docker-compose.backend.yml exec api alembic history
```

If the API is down:

```bash
docker compose --env-file .env.backend -f docker-compose.backend.yml \
  run --rm api alembic current
```

Do not run `alembic downgrade` during ordinary recovery. Application rollbacks
usually leave the database at the newer schema unless a downgrade was designed
and tested for that migration.

## 8. Create or reset a super-admin

When the API is running:

```bash
docker compose \
  --env-file .env.backend \
  -f docker-compose.backend.yml \
  exec api python -m app.cli create-admin \
  --email your-email@example.com
```

If the API is down:

```bash
docker compose \
  --env-file .env.backend \
  -f docker-compose.backend.yml \
  run --rm api python -m app.cli create-admin \
  --email your-email@example.com
```

The CLI prompts for a password. If the normalized email exists, it resets the
password, reactivates the account, and grants super-admin access. Otherwise it
creates a new super-admin.

Do not pass the password on the command line because it can remain in shell
history.

## 9. Scheduler operations

Run one scheduler pass:

```bash
docker compose --env-file .env.backend -f docker-compose.backend.yml \
  exec scheduler python -m app.jobs
```

Restart and follow the scheduler:

```bash
docker compose --env-file .env.backend -f docker-compose.backend.yml restart scheduler
docker compose --env-file .env.backend -f docker-compose.backend.yml \
  logs -f --tail=100 scheduler
```

## 10. MySQL console

Open MySQL as root without exposing the password in shell history:

```bash
docker compose \
  --env-file .env.backend \
  -f docker-compose.backend.yml \
  exec mysql sh -lc \
  'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"'
```

Useful read-only SQL:

```sql
SHOW TABLES;
SELECT * FROM alembic_version;
SELECT id, email, is_active, is_super_admin FROM admin_users;
SELECT id, name, admin_id, status FROM events;
exit;
```

## 11. MySQL backup

Create and protect the backup directory:

```bash
cd ~/event-manager-service
mkdir -p backups
chmod 700 backups
```

Create a timestamped logical backup:

```bash
BACKUP_FILE="backups/event-manager-$(date -u +%Y%m%dT%H%M%SZ).sql"

docker compose \
  --env-file .env.backend \
  -f docker-compose.backend.yml \
  exec -T mysql sh -lc \
  'exec mysqldump --single-transaction --quick --routines --triggers --add-drop-table -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' \
  > "$BACKUP_FILE"

chmod 600 "$BACKUP_FILE"
test -s "$BACKUP_FILE"
ls -lh "$BACKUP_FILE"
tail -n 5 "$BACKUP_FILE"
```

The final lines should contain a `Dump completed` comment. Copy backups off the
VM; a backup on the same boot disk is not sufficient disaster recovery.

Optional compression and listing:

```bash
gzip "$BACKUP_FILE"
ls -lh backups/
```

## 12. MySQL restore

> [!CAUTION]
> Restoring a dump can replace current production tables and data. Verify the
> exact file and create a fresh, tested backup before proceeding.

Select and verify the exact backup:

```bash
RESTORE_FILE="backups/EXACT-BACKUP-FILENAME.sql"
test -s "$RESTORE_FILE"
ls -lh "$RESTORE_FILE"
```

Stop database clients while keeping MySQL running:

```bash
docker compose --env-file .env.backend -f docker-compose.backend.yml \
  stop api scheduler
```

Restore a plain SQL dump:

```bash
docker compose \
  --env-file .env.backend \
  -f docker-compose.backend.yml \
  exec -T mysql sh -lc \
  'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' \
  < "$RESTORE_FILE"
```

Restore a compressed dump:

```bash
gzip -dc backups/EXACT-BACKUP-FILENAME.sql.gz | \
  docker compose \
    --env-file .env.backend \
    -f docker-compose.backend.yml \
    exec -T mysql sh -lc \
    'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"'
```

Apply forward migrations and restart the application:

```bash
docker compose --env-file .env.backend -f docker-compose.backend.yml run --rm migrate
docker compose --env-file .env.backend -f docker-compose.backend.yml \
  up -d --no-build api scheduler caddy
docker compose --env-file .env.backend -f docker-compose.backend.yml \
  exec api alembic current
```

## 13. Memory, disk, and OOM checks

```bash
free -h
swapon --show
df -h /
docker stats --no-stream
docker system df
```

Check whether Linux killed a process because of memory pressure:

```bash
sudo journalctl -k --since "24 hours ago" | \
  grep -iE 'out of memory|oom|killed process'
```

Check Docker daemon problems:

```bash
sudo journalctl -u docker --since "2 hours ago" --no-pager
```

Some swap usage is normal on the 1 GB VM. Investigate repeated container
restarts, steadily rising idle swap, a full disk, or OOM messages.

## 14. Restart and recovery

### Restart services without rebuilding

```bash
docker compose --env-file .env.backend -f docker-compose.backend.yml restart api
docker compose --env-file .env.backend -f docker-compose.backend.yml restart scheduler
docker compose --env-file .env.backend -f docker-compose.backend.yml restart caddy
docker compose --env-file .env.backend -f docker-compose.backend.yml restart
```

> [!NOTE]
> `restart` does not load newly pulled source code. Use the deployment procedure
> when application code changed.

### Stop and start while preserving volumes

```bash
docker compose --env-file .env.backend -f docker-compose.backend.yml down
docker compose --env-file .env.backend -f docker-compose.backend.yml \
  up -d --no-build
```

### Recover Docker

```bash
sudo systemctl status docker --no-pager
sudo systemctl restart docker
docker compose --env-file .env.backend -f docker-compose.backend.yml \
  up -d --no-build
```

### Recover an API that fails after deployment

```bash
docker compose --env-file .env.backend -f docker-compose.backend.yml ps -a
docker compose --env-file .env.backend -f docker-compose.backend.yml \
  logs --tail=200 mysql migrate api
docker compose --env-file .env.backend -f docker-compose.backend.yml up -d mysql
docker compose --env-file .env.backend -f docker-compose.backend.yml run --rm migrate
docker compose --env-file .env.backend -f docker-compose.backend.yml \
  up -d --no-build api scheduler caddy
```

### Diagnose HTTPS when the API is healthy

```bash
docker compose --env-file .env.backend -f docker-compose.backend.yml \
  logs --tail=200 caddy
sudo ss -lntup | grep -E ':(80|443)\b'
getent ahostsv4 "$(sed -n 's/^CADDY_ADDRESS=//p' .env.backend)"
```

Confirm Oracle Cloud NSG ingress permits TCP ports 80 and 443. Do not expose
ports 8000 or 3306 publicly.

## 15. Safe cleanup

Inspect disk use first:

```bash
docker system df
docker image ls
docker volume ls
```

Safe, scoped cleanup commands:

```bash
# Prompts before removing stopped containers
docker container prune

# Removes dangling images
docker image prune -f

# Removes unused build cache
docker builder prune -f
```

After confirming the application is healthy, unused images can be removed more
aggressively:

```bash
docker image prune -a
```

Never use these for routine cleanup:

```text
docker compose down -v
docker volume prune
docker system prune --volumes
```

The database is stored in a named Docker volume. Removing that volume destroys
the production database unless a usable backup exists.

## 16. Identify the production database volume

```bash
MYSQL_CONTAINER="$(docker compose \
  --env-file .env.backend \
  -f docker-compose.backend.yml \
  ps -q mysql)"

docker inspect "$MYSQL_CONTAINER" \
  --format '{{range .Mounts}}{{println .Name "->" .Destination}}{{end}}'
```

The expected volume name is similar to:

```text
event-manager-backend_mysql-data
```

Do not remove it. The committed full-stack Oracle file has a different Compose
project name and can create a different, empty volume.

## 17. Recover from using the wrong Compose file

Inspect only the accidental project:

```bash
docker compose \
  --env-file .env.backend \
  -f docker-compose.oracle.yml \
  ps -a
```

If it created containers, remove only those containers and networks. Do not add
`-v`:

```bash
docker compose \
  --env-file .env.backend \
  -f docker-compose.oracle.yml \
  down --remove-orphans
```

Restore the correct backend-only stack:

```bash
docker compose \
  --env-file .env.backend \
  -f docker-compose.backend.yml \
  up -d --no-build --remove-orphans
```

## 18. Change the Vercel public URL

Edit `.env.backend`:

```bash
nano .env.backend
```

Set:

```dotenv
PUBLIC_APP_URL=https://YOUR-PROJECT.vercel.app
```

Validate and recreate the Python services so they receive the new value:

```bash
docker compose --env-file .env.backend -f docker-compose.backend.yml config --quiet
docker compose --env-file .env.backend -f docker-compose.backend.yml \
  up -d --no-build --force-recreate api scheduler
```

Verify the Vercel project environment:

```dotenv
API_INTERNAL_URL=https://YOUR-BACKEND-HOST
NEXT_PUBLIC_API_BASE=/api/v1
```

Test the proxy:

```bash
curl --fail-with-body https://YOUR-PROJECT.vercel.app/health/api
```

## 19. Protect production deployment files

The Compose file is version-controlled, but keep a private backup of the secret
environment file outside the Git repository:

```bash
mkdir -p ~/event-manager-deployment-backup
chmod 700 ~/event-manager-deployment-backup
cp docker-compose.backend.yml ~/event-manager-deployment-backup/
cp .env.backend ~/event-manager-deployment-backup/
chmod 600 ~/event-manager-deployment-backup/.env.backend
```

Never commit `.env.backend` or paste it into chat or logs. It contains database
and application secrets.

## 20. Day-to-day checklist

```bash
cd ~/event-manager-service

docker compose --env-file .env.backend -f docker-compose.backend.yml config --quiet
docker compose --env-file .env.backend -f docker-compose.backend.yml ps -a
docker compose --env-file .env.backend -f docker-compose.backend.yml \
  exec api alembic current

API_HOST="$(sed -n 's/^CADDY_ADDRESS=//p' .env.backend)"
curl --fail-with-body "https://${API_HOST}/health"

free -h
df -h /
docker stats --no-stream
```

## 21. Commands requiring extra caution

The following commands can destroy data or make recovery substantially harder.
Do not use them during routine maintenance:

```text
docker compose down -v
docker volume rm ...
docker volume prune
docker system prune --volumes
alembic downgrade ...
DELETE FROM events ...
DROP DATABASE event_manager
```

Always create and verify a backup before a database restore, schema
intervention, or manual deletion.
