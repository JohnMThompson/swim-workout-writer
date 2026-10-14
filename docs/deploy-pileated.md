# Pileated deployment runbook

This deploys the existing Flask/Gunicorn application to `/srv/apps/swim-workout-writer` on Pileated. Caddy is managed separately in `/srv/ingress`; this repository does not install or configure it. The app joins the external Docker bridge network `web` as `swim-writer:8000` and publishes no host port.

## Startup behavior and database safety

Pileated sets `INITIALIZE_DEFAULT_ADMIN=false`, so startup never creates or modifies administrator accounts. The configured administrator must already exist in MySQL before the Pileated application starts. `ADMIN_USERNAME` and `ADMIN_PASSWORD` are initial provisioning values for deployments where initialization is enabled; startup never changes an existing password or renames an account. Change a password intentionally through the application's authenticated account management flow (where available) or a reviewed, one-time administrative procedure; changing `.env` does not change the existing password.

The Pileated override requires a nonempty `DATABASE_URL`, rejects schema auto-creation, and disables insertion of default stroke mappings. Startup still checks for the existing required tables. The `uploads/` and `instance/` bind mounts are retained. Other than admin creation when the configured username is absent, startup operations are read-only against MySQL: required-table inspection only; default mappings are not inserted. The canonical locations file is only read at startup. Normal authenticated application actions can write workout, upload-session, or mapping data.

Because the DigitalOcean deployment initially shares this database, do not launch Pileated against the production `DATABASE_URL` until the admin-provisioning code has been reviewed and the runbook has been followed. Validate with an isolated scratch database first. If production initialization is required, first confirm the configured admin username already exists (or explicitly schedule first-time creation), and take the normal database backup.

## Configure and build

On Pileated, ensure Docker Compose is installed, `/srv/ingress` has created the external Docker network named `web`, and the app checkout is available at the target path:

```bash
sudo install -d -o "$USER" -g "$USER" /srv/apps/swim-workout-writer
cd /srv/apps/swim-workout-writer
```

Create an untracked `.env` file (it is ignored by Git) with deployment credentials. Do not put real values in tracked files or shell history:

```dotenv
SECRET_KEY=<long-random-secret>
DEBUG=false
AUTO_CREATE_SCHEMA=false
REQUIRE_DATABASE_URL=true
INITIALIZE_DEFAULT_ADMIN=false
INITIALIZE_DEFAULT_STROKE_MAPPINGS=false
DATABASE_URL=mysql+pymysql://<user>:<password>@<host>:3306/<database>
ADMIN_USERNAME=<initial-provisioning-username>
ADMIN_PASSWORD=<initial-provisioning-password>
UPLOAD_FOLDER=uploads
```

Use a URL-encoded password if it contains URL-reserved characters. Restrict file access and create persistent directories:

```bash
chmod 600 .env
mkdir -p uploads instance
```

Build and render the merged configuration:

```bash
docker compose -f docker-compose.yml -f docker-compose.pileated.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.pileated.yml build web
```

Do not start the service yet if `.env` points at the shared production database and production administrator behavior has not been reviewed.

## Safe validation before production connection

Use a disposable local MySQL instance/database, or another isolated MySQL test database with no production data. Set `DATABASE_URL` in `.env` to that test database, keep `AUTO_CREATE_SCHEMA=false`, and use a disposable copy of the required schema. To validate connectivity without modifying rows, execute a read-only query from the application container after it has started against that isolated database:

```bash
docker compose -f docker-compose.yml -f docker-compose.pileated.yml run --rm --no-deps web \
  python -c 'from sqlalchemy import create_engine, text; from swim_app import create_app; app=create_app(); e=create_engine(app.config["SQLALCHEMY_DATABASE_URI"]); print(e.connect().execute(text("SELECT 1")).scalar_one())'
```

This startup validates the schema without provisioning administrators; the configured administrator must already exist in the selected database. The SQL query itself is read-only. Run automated tests in the repository checkout (tests use in-memory SQLite):

```bash
python -m pytest
```

Then start against the isolated test database and verify effective networking and port configuration:

```bash
docker compose -f docker-compose.yml -f docker-compose.pileated.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.pileated.yml ps
docker compose -f docker-compose.yml -f docker-compose.pileated.yml port web 8000
docker inspect "$(docker compose -f docker-compose.yml -f docker-compose.pileated.yml ps -q web)" \
  --format '{{json .NetworkSettings.Networks}}'
```

`docker compose ... port web 8000` should print nothing, and the inspect output should include network `web` with alias `swim-writer`. Verify startup health from inside the container, without making the service public:

```bash
docker compose -f docker-compose.yml -f docker-compose.pileated.yml exec -T web \
  python -c 'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8000/healthz").read().decode())'
```

## Production cutover

Only after reviewing this change, verifying the existing admin account in the shared database, and approving the production start:

1. Back up the production database using the established database procedure.
2. Set the production `DATABASE_URL` in `.env`; verify it carefully without printing its credentials.
3. Build the same revision and start the app:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.pileated.yml up -d --build
   ```

4. Confirm the configured administrator already exists in MySQL, then confirm logs show successful startup and that the app has no restart loop. Do not run migrations or `create_all` as part of this deployment.
5. Verify the app through the existing Caddy route managed in `/srv/ingress` and check `/healthz`. Confirm login before performing any upload or save operation.

## Upload persistence check

Uploads are stored in the host `uploads/` bind mount. Test this only with a disposable image and isolated test database, since successful review may delete temporary uploads:

```bash
printf 'persistence-check\n' > uploads/pileated-persistence-check.txt
docker compose -f docker-compose.yml -f docker-compose.pileated.yml up -d --force-recreate web
test -f uploads/pileated-persistence-check.txt
rm uploads/pileated-persistence-check.txt
```

## Rollback

Keep the previously deployed revision available. To return to it, check out its commit and recreate the app with the same override and `.env`:

```bash
git checkout <previous-good-commit>
docker compose -f docker-compose.yml -f docker-compose.pileated.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.pileated.yml ps
```

If rollback follows a schema or data change, restore or repair the database using the database backup procedure; rolling back the container does not reverse database writes. The app does not perform schema changes automatically in this deployment.
