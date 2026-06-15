# Swim Workout Writer

Private mobile-friendly web app for uploading Apple Workouts swim screenshots, reviewing parsed workout fields, and writing them to a MySQL-compatible database.

The production workout destination table is `swim_tracking`.
In production, schema auto-creation should remain disabled so startup fails fast if required tables are missing.

<img width="1156" height="646" alt="image" src="https://github.com/user-attachments/assets/14ff8e2d-691e-4593-ae04-741a428f49bd" />

## Features
- Single-user login
- Screenshot upload from mobile
- OCR extraction using `tesseract`
- Review/edit flow before saving
- Persistent stroke mappings such as `Kickboard -> Freestyle`
- Immediate writes after confirmation

## Local setup
1. Copy `.env.example` to `.env` and set credentials.
2. Install dependencies: `pip install -r requirements.txt`
3. Run the app: `python app.py`
4. Open `http://127.0.0.1:8000`

Default local storage uses SQLite. Point `DATABASE_URL` at MySQL in production, for example:

```bash
DATABASE_URL=mysql+pymysql://user:password@host:3306/database_name
```

For local SQLite development, schema is auto-created by default. For production-style deployments, set:

```bash
AUTO_CREATE_SCHEMA=false
```

## Docker
```bash
docker compose up --build
```

## Production deployment

Production uses:
- `docker-compose.yml` for the app service
- `docker-compose.prod.yml` for standalone production with its own Caddy
- `docker-compose.analytics.yml` for deployment on the existing analytics droplet with shared Caddy
- `deploy/Caddyfile` for HTTPS reverse proxying

For shared-Caddy deployment, set `SHARED_PROXY_NETWORK` in `.env` to the external Docker network used by the existing reverse proxy stack.

See [docs/deploy-digitalocean.md](/home/john/git-repos/swim-workout-writer/docs/deploy-digitalocean.md) for the DigitalOcean deployment runbook.

## Release checklist

Before release:
- Confirm `git status --short` is clean and the target branch is up to date.
- Run `pytest`.
- Review pending migrations or schema assumptions; production should keep `AUTO_CREATE_SCHEMA=false`.
- Verify required environment values are set: `SECRET_KEY`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `DATABASE_URL`, `UPLOAD_FOLDER`, and deployment-specific proxy settings.

After deploy:
- Confirm the deployment completed without container restart loops.
- Verify `GET /healthz` returns `{"status":"ok"}`.
- Open the app, confirm the login page loads, and complete a valid login.
- Spot-check the upload/review flow before relying on the release.

Rollback reminder:
- If verification fails, redeploy the last known good commit using the rollback steps in [docs/deploy-digitalocean.md](/home/john/git-repos/swim-workout-writer/docs/deploy-digitalocean.md#9-rollback).

## Notes
- Unknown stroke labels can be mapped permanently from the review screen.
- Uploaded screenshots are stored in `uploads/`.
- The app creates the single admin account on first boot from `ADMIN_USERNAME` and `ADMIN_PASSWORD`.
