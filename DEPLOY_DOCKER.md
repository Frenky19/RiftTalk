# Docker + CI/CD Deploy (Server Only)

This deploys only the server side with Redis. The client is shipped as `.exe`
to users and is not installed on the VPS.

## 1) Server initial setup (one-time)

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Install docker compose (if not included)
sudo apt-get update
sudo apt-get install -y docker-compose-plugin
```

Clone repo:
```bash
mkdir -p /opt/rifttalk
cd /opt
git clone YOUR_REPO_URL rifttalk
```

Create `server/.env` on the VPS (do NOT commit it):
```
APP_MODE=server
SERVER_HOST=0.0.0.0
SERVER_PORT=8001
REDIS_URL=redis://redis:6379
RIFT_SHARED_KEY=YOUR_LONG_RANDOM_SECRET
DISCORD_BOT_TOKEN=...
DISCORD_GUILD_ID=...
DISCORD_OAUTH_CLIENT_ID=...
DISCORD_OAUTH_CLIENT_SECRET=...
PUBLIC_BASE_URL=https://your-domain.com
JWT_SECRET_KEY=YOUR_LONG_RANDOM_SECRET
```

First run:
```bash
cd /opt/rifttalk
docker compose up -d --build
```

## 1.1) Nginx + HTTPS (Let's Encrypt)

Edit `nginx/conf.d/rifttalk.conf` and replace `your-domain.com` with your domain.
Make sure DNS A/AAAA points to the VPS.

Issue the first certificate:
```bash
docker compose run --rm certbot certonly \
  --webroot -w /var/www/certbot \
  -d your-domain.com \
  --email you@example.com --agree-tos --no-eff-email
```

Reload nginx:
```bash
docker compose exec nginx nginx -s reload
```

If you add multiple domains, run certbot with multiple `-d` flags.

## 2) GitHub Actions CI/CD

This repo includes `.github/workflows/deploy.yml` which connects to the server
via SSH and runs `docker compose up -d --build`.

Add these GitHub secrets:
- `SSH_HOST` — server IP or domain
- `SSH_USER` — SSH user (e.g. ubuntu)
- `SSH_KEY` — private key for that user (PEM format)
- `SSH_PORT` — usually 22
- `DEPLOY_PATH` — `/opt/rifttalk`

## 3) Health check

After deploy:
```
GET https://your-domain.com/health
```
Redis should show `healthy`.
