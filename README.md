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
B. Navidrome Credentials
- NAVIDROME_ADMIN_USER / NAVIDROME_ADMIN_PASSWORD: Credentials for the
  Navidrome admin account. The bot uses these to trigger library scans.
  The docker-compose stack will auto-generate /data/navidrome.toml with
  DevAutoCreateAdminPassword set to NAVIDROME_ADMIN_PASSWORD so Navidrome
  comes up with a ready admin account each time.
C. Host Mount Paths (CRITICAL)
These define the HOST directory paths where your remote storage is mounted.
- HOST_SLSKD_DATA: Absolute host path where slskd should persist its internal
  database, cache, and logs. Example: /srv/slskd/data (create it locally).
- HOST_DOWNLOADS_PATH: The absolute path on your host OS where your completed
  downloads remote folder is mounted. This path is shared between slskd and Navidrome.
  *Example: /mnt/remote/music/slskd_downloads
- HOST_SHARES_PATH: The absolute path on your host OS where your slskd share folder is mounted.
  *Example: /mnt/remote/music/slskd_shares
--- 2. RUNNING THE SYSTEM ---
1. Build and Start: Open a terminal in your project directory and run:
   ./scripts/setup_and_compose.sh
   - The script ensures your bind-mount directories exist with write permissions and
     then runs `docker compose up -d --build` (pass extra args to forward them).
   - The helper containers run automatically to inject navidrome.toml and slskd.yml,
     then exit.
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
- `!dl <number>`: Queues the numbered entry from your most recent search result. Only file downloads are supported today.
- `!progress` / `!status`: Shows the current download queue with progress bars, regardless of who requested the transfer.
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
