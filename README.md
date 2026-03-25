# Swim Workout Writer

Private mobile-friendly web app for uploading Apple Workouts swim screenshots, reviewing parsed workout fields, and writing them to a MySQL-compatible database.

The production workout destination table is `swim_tracking`.

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

## Notes
- Unknown stroke labels can be mapped permanently from the review screen.
- Uploaded screenshots are stored in `uploads/`.
- The app creates the single admin account on first boot from `ADMIN_USERNAME` and `ADMIN_PASSWORD`.
