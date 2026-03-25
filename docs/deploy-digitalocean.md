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
- `DEBUG=false`
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

The app container should now be reachable on the shared Docker network as `swim-workout-writer-web-1:8000`.

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
    reverse_proxy swim-workout-writer-web-1:8000
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
- If the MySQL droplet has a firewall, allow inbound MySQL only from the analytics droplet IP.
