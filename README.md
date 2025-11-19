Slskd Discord Bot & Navidrome Server (Docker Setup)

This file serves as your complete guide for setting up and running the
multi-container application using Docker Compose.
--- OVERVIEW ---
This setup orchestrates three services:
1. slskd: The Soulseek server and API.
2. discord-bot: Your Python bot that interacts with slskd and Discord.
3. navidrome: The music streaming server.
Plus two short-lived helpers:
- navidrome-config: Generates /data/navidrome.toml with the admin bootstrap password.
- slskd-config: Templates slskd.yml with your secrets into the slskd data directory.

PIPELINE: The bot detects completed downloads, then automatically triggers
Navidrome to scan the new file, making it immediately available for streaming.
--- PREREQUISITES ---
1. Docker and Docker Compose: Must be installed on your host machine.
2. Remote Storage Mounted: Your remote storage (SSHFS, WebDAV, etc.) must be
   mounted locally on your host machine *before* you run Docker Compose.
3. Required Files: Ensure all necessary files are present in the same directory:
   - docker-compose.yml
   - Dockerfile
   - slskd_discord_bot.py
   - requirements.txt
   - .env
   - slskd.yml (acts as a template using ${ENV_VAR} placeholders; the stack
     renders it into HOST_SLSKD_DATA/slskd.yml before slskd starts)
--- 1. CONFIGURATION (.env file) ---
You MUST create a file named .env and fill in all the required variables.
A. Discord & Soulseek Secrets
- DISCORD_BOT_TOKEN: Your Discord bot token.
- SLSK_USERNAME / SLSK_PASSWORD: Your Soulseek login credentials.
- SLSKD_API_KEY: A long, random key you create. This secures the slskd API.
- SLSKD_ADMIN_USER / SLSKD_ADMIN_PASSWORD: Credentials for the slskd web UI login.
- SLSKD_DOMAIN / NAVIDROME_DOMAIN: Public FQDNs that route to your VPS (e.g., slskd.cratedaemon.space).
- LETSENCRYPT_EMAIL: Email used for Let's Encrypt expiry notices.
B. Navidrome Credentials
- NAVIDROME_ADMIN_USER / NAVIDROME_ADMIN_PASSWORD: Credentials for the
  Navidrome admin account. The bot uses these to trigger library scans.
  The docker-compose stack will auto-generate /data/navidrome.toml with
  DevAutoCreateAdminPassword set to NAVIDROME_ADMIN_PASSWORD so Navidrome
  comes up with a ready admin account each time.
C. Host Mount Paths (CRITICAL)
These define the HOST directory paths where your remote storage is mounted.
- HOST_MEDIA_PATH: Single directory (usually an SSHFS mount) that contains all
  downloaded media. Both HOST_DOWNLOADS_PATH and HOST_SHARES_PATH reference this
  path downstream.
- HOST_DOWNLOADS_PATH / HOST_SHARES_PATH: Typically set to `${HOST_MEDIA_PATH}`.
- HOST_SLSKD_DATA: Absolute host path where slskd should persist its internal
  database, cache, and logs. Example: /srv/slskd/data (create it locally).
- HOST_NAVIDROME_DATA: Absolute host path where Navidrome should persist its database/cache.
  *Example: /srv/navidrome/data
  *Note: slskd automatically shares the downloads directory so finished files become available to other users.
D. Hetzner Storage Box (SSHFS) Details
- STORAGEBOX_HOST / STORAGEBOX_PORT / STORAGEBOX_USER: Connection info for your
  Hetzner Storage Box.
- STORAGEBOX_PASSWORD: Used once to install the SSH key (script prompts only if set here).
- STORAGEBOX_REMOTE_PATH: Directory on the storage box where media should live (created automatically).
--- INITIAL SYSTEM SETUP (Ubuntu 24.04) ---
1. Copy `.env` onto the VPS and fill in all required variables (domains, storage
   credentials, media paths, etc.).
2. Install dependencies and configure the SSHFS mount:
   sudo ./scripts/install_system.sh
   - Installs Docker, docker-compose plugin, git, sshfs, sshpass, openssl.
   - Generates an SSH key (if missing), installs it on the Hetzner Storage Box,
     creates the remote directory, enables `user_allow_other`, and configures a
     systemd automount that reconnects automatically.
3. Log out/log back in (or `newgrp docker`) if you want to run Docker commands without sudo.

--- 2. RUNNING THE SYSTEM ---
1. Build and Start (Dev): Open a terminal in your project directory and run:
   ./scripts/setup_dev.sh
   - Ensures bind-mounts exist and launches the stack with the development nginx config (slskd.localhost/navidrome.localhost).
   - Update your `/etc/hosts` (or OS equivalent) with `127.0.0.1 slskd.localhost navidrome.localhost` to access the UIs locally.
2. Build and Start (Prod): Once DNS for `SLSKD_DOMAIN`/`NAVIDROME_DOMAIN` points to your VPS (both records should resolve to the server's public IP), run:
   ./scripts/setup_prod.sh
   - Renders `config/nginx.prod.conf` from `.env`, ensures bind mounts and the `certbot/` directories exist, generates a temporary self-signed cert (so nginx can boot), and launches the stack via `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`.
   - After nginx is up, the script runs `certbot-init` once to request Let's Encrypt certificates for both domains, then reloads nginx to start serving HTTPS immediately.
   - The always-on `certbot-renew` service (defined in `docker-compose.prod.yml`) runs `certbot renew` every ~12h and sends `HUP` to nginx when certificates change, making renewals hands-free.
   - To redeploy, simply rerun `./scripts/setup_prod.sh`; it will reuse existing certs and config.
2. Verify Service Health: Check the status of your containers. Ensure 'slskd'
   is *healthy* before the bot will start interacting with it.
   docker-compose ps
3. Accessing Services:
   - Discord Bot: Use it in your Discord server (!search, !dl).
   - Navidrome UI: Access the web interface at http://localhost:4533.
     Log in with your NAVIDROME_ADMIN_USER/PASSWORD.
4. Monitoring Logs: To see real-time output from all services:
   docker-compose logs -f
   To focus on the bot's activity:
   docker-compose logs -f discord-bot
--- 2a. DISCORD BOT COMMANDS ---
- `!search <query>`: Runs a Soulseek search through slskd and returns a paginated embed of up to 10 results per page. Use the buttons to page through results.
- `!dl <number>`: Queues the numbered entry from your most recent search result. Files download one-by-one; folders queue every file inside while preserving the remote directory structure.
- `!progress` / `!status`: Shows the current download queue with progress bars, regardless of who requested the transfer.
- `!help`: Displays this command cheat sheet inside Discord.
- Buttons: The paginator view adds `First/Prev/Next/Last` navigation plus a `Cancel Search` button to drop cached results if you no longer need them.
--- 3. STOPPING AND CLEANING UP ---
1. Stop Containers (Data Kept):
   docker-compose down
   - This stops the containers, but keeps all downloaded files (on your host mount)
     and preserves the 'navidrome_data' volume (database/cache).
2. Stop and Remove All Data:
   docker-compose down -v
   - This stops the containers AND removes the persistent 'navidrome_data' named volume.
     It does NOT delete files stored on your host machine via the bind mounts.
