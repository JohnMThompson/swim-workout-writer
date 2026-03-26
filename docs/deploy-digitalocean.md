# DigitalOcean Deployment Runbook

This deploys `swim-workout-writer` to the existing analytics droplet as a separate Docker Compose stack, using the already-running Caddy container from `analytics-hub` for HTTPS and hostname routing.

## 1. Recommended topology

- Deploy this app on the existing analytics droplet
- Keep MySQL on the database droplet
- Expose the app on its own subdomain, for example `swim-writer.johnthompson.io`
- Restrict MySQL access so only the analytics droplet can connect
- Reuse the existing `ai-analytics` Docker network and Caddy instance

## 2. DNS setup

Create an `A` record for the app subdomain pointing to the analytics droplet public IP.

Example:
- Host: `swim-writer`
- Type: `A`
- Value: `<ANALYTICS_DROPLET_PUBLIC_IP>`

## 3. Droplet bootstrap

If Docker and the Compose plugin are already installed for `analytics-hub`, reuse that setup. Otherwise:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg ufw git

sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker "$USER"
```

Re-login or run `newgrp docker`.

## 4. Firewall

Allow only SSH, HTTP, and HTTPS on the droplet:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable
sudo ufw status
```

Do not expose port `8000` publicly.

## 5. App checkout and environment

```bash
sudo mkdir -p /opt/swim-workout-writer
sudo chown "$USER":"$USER" /opt/swim-workout-writer
git clone https://github.com/JohnMThompson/swim-workout-writer.git /opt/swim-workout-writer
cd /opt/swim-workout-writer
cp .env.example .env
mkdir -p uploads instance
```

Edit `/opt/swim-workout-writer/.env` with production values:

- `APP_DOMAIN=swim-writer.johnthompson.io`
- `SHARED_PROXY_NETWORK=ai-analytics_ai-analytics`
- `DEBUG=false`
- `AUTO_CREATE_SCHEMA=false`
- `SECRET_KEY=<long random value>`
- `ADMIN_USERNAME=<your login>`
- `ADMIN_PASSWORD=<strong password>`
- `DATABASE_URL=mysql+pymysql://<user>:<password>@<db-host>:3306/<db-name>`
- `UPLOAD_FOLDER=uploads`

## 6. First deploy

This app should not publish `80` or `443`, and it should not run its own Caddy container on the analytics droplet.

```bash
cd /opt/swim-workout-writer
docker compose -f docker-compose.yml -f docker-compose.analytics.yml up -d --build
```

Verify:

```bash
docker compose -f docker-compose.yml -f docker-compose.analytics.yml ps
docker ps --format '{{.Names}}'
```

The app container should now be reachable on the shared Docker network through the stable alias `swim-workout-writer:8000`.

## 7. Caddy route on the analytics stack

Edit the Caddyfile used by `analytics-hub` and add a new site block:

```caddy
swim-writer.johnthompson.io {
  encode zstd gzip

  @blocked {
    path /.env /.env.* /.git /.git/* /.vscode /.vscode/* /server-status /console /console/*
  }

  route {
    respond @blocked 404
    reverse_proxy swim-workout-writer:8000
  }

  header {
    Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
    X-Content-Type-Options "nosniff"
    X-Frame-Options "SAMEORIGIN"
    Referrer-Policy "strict-origin-when-cross-origin"
  }

  log {
    output stdout
    format console
  }
}
```

Then reload the existing analytics Caddy container:

```bash
cd /opt/ai-analytics
docker compose exec caddy caddy reload --config /etc/caddy/Caddyfile
```

Verify:

```bash
curl -fsS https://swim-writer.johnthompson.io/healthz
```

Then open `https://swim-writer.johnthompson.io` and verify login, upload, review, and save.

## 8. Manual deploy updates

```bash
cd /opt/swim-workout-writer
git fetch origin
git pull --ff-only origin main
docker compose -f docker-compose.yml -f docker-compose.analytics.yml up -d --build
```

## 8a. GitHub Actions deploy automation

The repo includes a GitHub Actions workflow at `.github/workflows/deploy.yml`.
It deploys on pushes to `main` and can also be run manually from the Actions tab.

Configure these repository secrets before enabling production deploys:

- `DEPLOY_HOST`: analytics droplet hostname or IP
- `DEPLOY_PORT`: SSH port, usually `22` (optional)
- `DEPLOY_USER`: SSH user on the droplet
- `DEPLOY_SSH_KEY`: private SSH key for that user
- `DEPLOY_APP_DIR`: app checkout path on the droplet, for example `/opt/swim-workout-writer`
- `DEPLOY_HEALTHCHECK_URL`: public health check URL, for example `https://swim-writer.johnthompson.io/healthz`

The workflow performs the same deploy steps as the manual runbook:

```bash
cd /opt/swim-workout-writer
git fetch origin
git pull --ff-only origin main
docker compose -f docker-compose.yml -f docker-compose.analytics.yml up -d --build
curl -fsS https://swim-writer.johnthompson.io/healthz
```

Recommended hardening:

- Store the workflow in the `production` GitHub environment
- Require approval for that environment if you want a manual gate before deploys
- Use a deploy-specific SSH key instead of a personal key
- Ensure the deploy user can run `docker compose` without interactive sudo

## 9. Rollback

```bash
cd /opt/swim-workout-writer
git log --oneline -n 20
git checkout <GOOD_SHA>
docker compose -f docker-compose.yml -f docker-compose.analytics.yml up -d --build
```

If you use rollback often, replace detached checkouts with a branch-based procedure.

## 10. Notes

- `uploads/` is only transient review storage; files are deleted after successful saves.
- `instance/` is mounted so SQLite local testing and any instance state stay outside the container filesystem.
- This app does not run its own Caddy container on the analytics droplet.
- The shared proxy network name is provided by `SHARED_PROXY_NETWORK` so the repo does not hardcode droplet-specific Docker metadata.
- If the MySQL droplet has a firewall, allow inbound MySQL only from the analytics droplet IP.
