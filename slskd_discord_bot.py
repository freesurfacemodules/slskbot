import discord
from discord.ext import commands, tasks
from discord.ui import View, Button, button
import aiohttp
import asyncio
import os
import logging
from typing import Dict, Any, List, Optional

import typing as _typing

if not hasattr(_typing, "NotRequired"):
    from typing_extensions import NotRequired as _NotRequired  # type: ignore

    setattr(_typing, "NotRequired", _NotRequired)

import requests
from slskd_api import SlskdClient

# --- Configuration ---
# Set these environment variables before running the bot
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
SLSKD_API_URL = os.environ.get(
    "SLSKD_API_URL", "http://localhost:5030"
)  # e.g., "http://your-slskd-ip:5030"
SLSKD_API_KEY = os.environ.get("SLSKD_API_KEY")

# --- New Navidrome Configuration ---
NAVIDROME_URL = "http://navidrome:4533"  # Internal Docker service name
NAVIDROME_ADMIN_USER = os.environ.get("NAVIDROME_ADMIN_USER")
NAVIDROME_ADMIN_PASSWORD = os.environ.get("NAVIDROME_ADMIN_PASSWORD")

# Check for essential configuration
if not DISCORD_BOT_TOKEN:
    print("Error: DISCORD_BOT_TOKEN environment variable not set.")
    exit(1)
if not SLSKD_API_KEY:
    print("Error: SLSKD_API_KEY environment variable not set.")
    exit(1)

# --- Bot Setup ---
intents = discord.Intents.default()
intents.message_content = True  # Required for message-based commands
bot = commands.Bot(command_prefix="!", intents=intents)

# --- Logging ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("slskd-bot")


class AsyncSlskdClient:
    """Async wrapper around the slskd-api synchronous client."""

    def __init__(self, base_url: str, api_key: str):
        host = base_url.rstrip("/")
        self._client = SlskdClient(host=host, api_key=api_key, url_base="")

    async def close(self):
        await asyncio.to_thread(self._client.session.close)

    async def start_search(self, query: str) -> Optional[str]:
        state = await self._call(self._client.searches.search_text, query)
        if state and state.get("id"):
            logger.info(f"Started search for '{query}', ID: {state['id']}")
            return state["id"]
        logger.error(f"Failed to start search for '{query}'. Response: {state}")
        return None

    async def get_search_state(self, search_id: str) -> Optional[Dict[str, Any]]:
        return await self._call(self._client.searches.state, search_id)

    async def get_search_results(self, search_id: str) -> Optional[List[Dict[str, Any]]]:
        return await self._call(self._client.searches.search_responses, search_id)

    async def enqueue_files(
        self, username: str, files: List[Dict[str, Any]]
    ) -> Optional[bool]:
        if not files:
            return False
        return await self._call(self._client.transfers.enqueue, username, files)

    async def get_all_downloads(self) -> Optional[List[Dict[str, Any]]]:
        return await self._call(self._client.transfers.get_all_downloads, False)

    async def get_application_state(self) -> Optional[Dict[str, Any]]:
        return await self._call(self._client.application.state)

    async def _call(self, func, *args, **kwargs):
        try:
            return await asyncio.to_thread(func, *args, **kwargs)
        except requests.exceptions.RequestException as exc:
            logger.error(f"slskd API request failed: {exc}")
            return None


# --- Bot State & Pagination ---

# In-memory storage for search results and tracked downloads
# { user_id: [list_of_search_results] }
user_search_results: Dict[int, List[Dict[str, Any]]] = {}
# { "username:filename": { ...info... } }
tracked_downloads: Dict[str, Dict[str, Any]] = {}

cog_instance: Optional["SlskdCog"] = None  # Populated once the cog loads


def make_transfer_key(username: str, path: Optional[str]) -> str:
    """Creates a normalized key for tracking downloads."""
    safe_username = username or "unknown"
    safe_path = (path or "").rsplit("/", 1)[-1]
    return f"{safe_username}:{safe_path.lower()}"


class SearchResultPaginator(View):
    """
    A Discord View for paginating through slskd search results.
    """

    def __init__(
        self, ctx: commands.Context, results: List[Dict[str, Any]], query: str
    ):
        super().__init__(timeout=300)  # 5-minute timeout
        self.ctx = ctx
        self.query = query
        self.all_results = self.flatten_results(results)
        self.per_page = 10
        self.current_page = 0
        self.total_pages = -(
            -len(self.all_results) // self.per_page
        )  # Ceiling division

        # Store these results for the '!dl' command
        user_search_results[ctx.author.id] = self.all_results

        self.update_buttons()

    def flatten_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Flattens the nested slskd result structure into a list of downloadable items."""
        flat_list = []
        for response_group in results:
            username = response_group.get("username")
            token = response_group.get("token")

            if not username or not token:
                continue

            # Add files
            for file_info in response_group.get("files", []):
                filename = file_info.get("filename", "")
                flat_list.append(
                    {
                        "type": "file",
                        "username": username,
                        "token": token,
                        "file": file_info,
                        "path": filename,
                        "size_mb": round(file_info.get("size", 0) / (1024 * 1024), 2),
                        "slots_free": response_group.get("hasFreeUploadSlot", False),
                        "speed_kb": round(
                            response_group.get("uploadSpeed", 0) / 1024, 2
                        ),
                    }
                )

            # Add directories
            # NOTE: slskd search API (v0) doesn't seem to return directories in the same way
            # as files. We'll focus on file downloads as it's more reliable.
            # If folder search is desired, it's often done via browsing.

        return flat_list

    def get_page_embed(self) -> discord.Embed:
        """Creates an embed for the current page of results."""
        embed = discord.Embed(
            title=f"Search Results for '{self.query}'", color=discord.Color.blue()
        )

        if not self.all_results:
            embed.description = "No results found."
            return embed

        start_index = self.current_page * self.per_page
        end_index = start_index + self.per_page

        description_lines = []
        for i, item in enumerate(
            self.all_results[start_index:end_index], start=start_index + 1
        ):
            slots = "✅" if item["slots_free"] else "❌"
            line = (
                f"**{i}.** {item['path'].split('/')[-1]}\n"
                f"   `[{item['type']}]` `[{item['size_mb']} MB]` `[{slots} Slot]` `[User: {item['username']}]`"
            )
            description_lines.append(line)

        embed.description = "\n".join(description_lines)
        embed.set_footer(
            text=f"Page {self.current_page + 1} of {self.total_pages} | Total Results: {len(self.all_results)}\n"
            f"Use !dl <number> to download."
        )
        return embed

    async def update_message(self, interaction: discord.Interaction):
        """Updates the message with the new embed and button states."""
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_page_embed(), view=self)

    def update_buttons(self):
        """Disables/Enables buttons based on the current page."""
        self.prev_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page >= self.total_pages - 1
        self.first_page_button.disabled = self.current_page == 0
        self.last_page_button.disabled = self.current_page >= self.total_pages - 1

    @button(label="<< First", style=discord.ButtonStyle.secondary, row=0)
    async def first_page_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.ctx.author:
            await interaction.response.send_message(
                "This is not your search.", ephemeral=True
            )
            return
        self.current_page = 0
        await self.update_message(interaction)

    @button(label="< Prev", style=discord.ButtonStyle.primary, row=0)
    async def prev_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.ctx.author:
            await interaction.response.send_message(
                "This is not your search.", ephemeral=True
            )
            return
        self.current_page -= 1
        await self.update_message(interaction)

    @button(label="Next >", style=discord.ButtonStyle.primary, row=0)
    async def next_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.ctx.author:
            await interaction.response.send_message(
                "This is not your search.", ephemeral=True
            )
            return
        self.current_page += 1
        await self.update_message(interaction)

    @button(label="Last >>", style=discord.ButtonStyle.secondary, row=0)
    async def last_page_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.ctx.author:
            await interaction.response.send_message(
                "This is not your search.", ephemeral=True
            )
            return
        self.current_page = self.total_pages - 1
        await self.update_message(interaction)

    @button(label="Cancel Search", style=discord.ButtonStyle.danger, row=1)
    async def cancel_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.ctx.author:
            await interaction.response.send_message(
                "This is not your search.", ephemeral=True
            )
            return

        if self.ctx.author.id in user_search_results:
            del user_search_results[self.ctx.author.id]

        await interaction.response.edit_message(
            content="Search cancelled and results cleared.", embed=None, view=None
        )
        self.stop()

    async def on_timeout(self):
        # Clear results on timeout
        if self.ctx.author.id in user_search_results:
            del user_search_results[self.ctx.author.id]

        # Disable view
        for item in self.children:
            item.disabled = True
        # Check if message exists before editing
        try:
            await self.message.edit(content="Search timed out.", embed=None, view=self)
        except discord.NotFound:
            pass  # Message was deleted


# --- Bot Cog ---
class SlskdCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.api = AsyncSlskdClient(SLSKD_API_URL, SLSKD_API_KEY)
        self.download_monitor.start()

    def cog_unload(self):
        self.download_monitor.cancel()
        asyncio.create_task(self.api.close())
        logger.info("SlskdCog unloaded, API session close scheduled.")

    async def trigger_navidrome_scan(self):
        """Triggers a library scan on the Navidrome server."""
        if not NAVIDROME_ADMIN_USER or not NAVIDROME_ADMIN_PASSWORD:
            logger.warning(
                "NAVIDROME_ADMIN_USER or NAVIDROME_ADMIN_PASSWORD not set. Skipping Navidrome scan."
            )
            return

        scan_url = f"{NAVIDROME_URL}/api/v1/scan"
        auth = aiohttp.BasicAuth(NAVIDROME_ADMIN_USER, NAVIDROME_ADMIN_PASSWORD)

        logger.info("Triggering Navidrome library scan...")
        try:
            # We create a new session here to avoid any header conflicts with the slskd API client
            async with aiohttp.ClientSession() as session:
                async with session.post(scan_url, auth=auth, timeout=30) as response:
                    if 200 <= response.status < 300:
                        logger.info("Navidrome scan triggered successfully.")
                    else:
                        logger.error(
                            f"Failed to trigger Navidrome scan. Status: {response.status}, Body: {await response.text()}"
                        )
        except aiohttp.ClientConnectorError:
            logger.error(
                f"Could not connect to Navidrome at {scan_url}. Is it running?"
            )
        except asyncio.TimeoutError:
            logger.error(f"Timed out trying to trigger Navidrome scan.")
        except Exception as e:
            logger.error(f"An error occurred while triggering Navidrome scan: {e}")

    @commands.command(name="search")
    async def search(self, ctx: commands.Context, *, query: str):
        """Searches slskd for a query.
        Example: !search <your search query>
        """
        logger.info(f"User {ctx.author} starting search for: {query}")
        msg = await ctx.reply(
            f"🔍 Starting search for `{query}`... this may take a moment."
        )

        search_id = await self.api.start_search(query)
        if not search_id:
            await msg.edit(
                content=f"Sorry, I failed to start the search on slskd. Check my logs."
            )
            return

        # Poll for results
        results = None
        for _ in range(10):  # Poll for 10 seconds (10 * 1s)
            await asyncio.sleep(1)
            status = await self.api.get_search_state(search_id)
            if status and status.get("isComplete"):
                logger.info(f"Search {search_id} for '{query}' is complete.")
                results = await self.api.get_search_results(search_id)
                break
            elif not status:
                await msg.edit(content=f"Error checking search status for `{query}`.")
                return

        if not results:
            # Check if search timed out but got *some* results
            results = await self.api.get_search_results(search_id)
            if not results:
                await msg.edit(
                    content=f"Search for `{query}` completed with no results."
                )
                return

        # We have results, send the paginator
        paginator = SearchResultPaginator(ctx, results, query)
        paginator.message = await msg.edit(
            content=None, embed=paginator.get_page_embed(), view=paginator
        )

    @commands.command(name="dl", aliases=["download"])
    async def download(self, ctx: commands.Context, number: int):
        """Downloads a file or folder from your last search.
        Example: !dl 5
        """
        if ctx.author.id not in user_search_results:
            await ctx.reply(
                "You don't have any active search results. Please use `!search` first."
            )
            return

        results = user_search_results[ctx.author.id]

        # Adjust for 1-based indexing
        index = number - 1

        if not (0 <= index < len(results)):
            await ctx.reply(
                f"Invalid number. Please pick a number between 1 and {len(results)}."
            )
            return

        item = results[index]

        try:
            if item["type"] != "file":
                await ctx.reply("Folder downloads are not supported yet.")
                return

            file_payload = dict(item["file"])
            file_payload["token"] = item["token"]
            success = await self.api.enqueue_files(item["username"], [file_payload])
            if not success:
                await ctx.reply("Failed to queue download. Please try again.")
                return

            filename = item["path"].split("/")[-1]
            await ctx.reply(f"✅ Queued for download: `{filename}`")

            transfer_key = make_transfer_key(item["username"], item["path"])
            tracked_downloads[transfer_key] = {
                "user_id": ctx.author.id,
                "channel_id": ctx.channel.id,
                "filename": filename,
                "notified": False,
                "search_path": item["path"],
            }

        except Exception as e:
            logger.error(f"Error during !dl command: {e}")
            await ctx.reply(
                f"An error occurred while trying to queue the download: {e}"
            )

    @commands.command(name="progress", aliases=["status"])
    async def progress(self, ctx: commands.Context):
        """Shows the status of your ongoing slskd downloads."""
        transfers = await self.api.get_all_downloads()
        if transfers is None:
            await ctx.reply(
                "Could not retrieve download status or no active transfers."
            )
            return
        if not transfers:
            await ctx.reply("No active downloads found.")
            return

        user_downloads = []
        for transfer in transfers:
            username = transfer.get("username")
            for directory in transfer.get("directories", []):
                for file_info in directory.get("files", []):
                    if file_info.get("direction") != "Download":
                        continue

                    state = file_info.get("state", "Unknown")
                    filename = file_info.get("filename", "N/A").split("/")[-1]
                    percent = file_info.get("percentComplete", 0) or 0
                    bar = "🟩" * int(percent / 10) + "⬜" * (10 - int(percent / 10))

                    user_downloads.append(
                        f"**{filename}** (from {username})\n`{state}` | {bar} | `{percent:.1f}%`"
                    )

        if not user_downloads:
            await ctx.reply("No active downloads found.")
            return

        embed = discord.Embed(
            title="Download Progress",
            description="\n\n".join(user_downloads),
            color=discord.Color.green(),
        )
        await ctx.reply(embed=embed)

    @tasks.loop(seconds=30)
    async def download_monitor(self):
        """Periodically checks for completed downloads and notifies users."""
        await self.bot.wait_until_ready()

        if not tracked_downloads:
            return  # No downloads to track

        try:
            transfers = await self.api.get_all_downloads()
            if transfers is None:
                return

            active_transfers: Dict[str, str] = {}
            completed_transfers = set()

            for transfer in transfers:
                username = transfer.get("username")
                for directory in transfer.get("directories", []):
                    for file_info in directory.get("files", []):
                        if file_info.get("direction") != "Download":
                            continue

                        key = make_transfer_key(username, file_info.get("filename"))
                        state = file_info.get("state")

                        if state == "Completed":
                            completed_transfers.add(key)
                        else:
                            active_transfers[key] = state

            # --- Modified Logic ---
            # We set a flag to only scan ONCE per loop, even if multiple files finish
            needs_navidrome_scan = False

            # Now check our tracked downloads
            for key, info in list(tracked_downloads.items()):
                if key in completed_transfers and not info["notified"]:
                    # This download finished! Notify the user.
                    try:
                        user = await self.bot.fetch_user(info["user_id"])
                        channel = await self.bot.fetch_channel(info["channel_id"])

                        if user and channel:
                            await channel.send(
                                f"{user.mention} Your download is complete: `{info['filename']}`"
                            )

                        # Mark as notified to avoid repeat messages
                        tracked_downloads[key]["notified"] = True
                        needs_navidrome_scan = True  # Set the flag

                        # Optional: Remove from tracking after a while
                        # For now, we'll just leave it as notified

                    except discord.NotFound:
                        logger.warning(
                            f"Could not find user/channel for completed download: {key}"
                        )
                    except Exception as e:
                        logger.error(f"Failed to send download completion notice: {e}")

                elif (
                    key not in active_transfers
                    and key not in completed_transfers
                    and not info["notified"]
                ):
                    # Transfer is no longer in the list, it was probably cleared or failed
                    # We'll remove it from tracking
                    logger.info(f"Removing untracked download: {key}")
                    del tracked_downloads[key]

            # After checking all files, trigger scan if needed
            if needs_navidrome_scan:
                await self.trigger_navidrome_scan()

        except Exception as e:
            logger.error(f"Error in download_monitor task: {e}")


# --- Bot Run ---
@bot.event
async def on_ready():
    global cog_instance
    logger.info(f"Logged in as {bot.user.name} (ID: {bot.user.id})")
    logger.info("Connecting to slskd API...")
    try:
        if bot.get_cog("SlskdCog") is None:
            cog_instance = SlskdCog(bot)
            await bot.add_cog(cog_instance)
            logger.info("SlskdCog added.")
        elif cog_instance is None:
            # Cog was already loaded (e.g., reconnect); capture reference
            existing = bot.get_cog("SlskdCog")
            if isinstance(existing, SlskdCog):
                cog_instance = existing

        server_state = None
        if cog_instance:
            state = await cog_instance.api.get_application_state()
            server_state = state.get("server") if state else None

        if server_state and server_state.get("isLoggedIn"):
            logger.info("Successfully connected to slskd API and user is logged in.")
        elif server_state:
            logger.warning("Connected to slskd API, but user is NOT logged in.")
        else:
            logger.error("Failed to get a valid response from slskd API on startup.")

    except Exception as e:
        logger.error(f"Failed to load SlskdCog: {e}")

    print("------")
    print(f"Bot is ready and online.")
    print("------")


def main():
    if not DISCORD_BOT_TOKEN or not SLSKD_API_KEY or not SLSKD_API_URL:
        print("---")
        print("ERROR: Missing one or more environment variables:")
        print(" - DISCORD_BOT_TOKEN (Your bot's token)")
        print(" - SLSKD_API_KEY (Your slskd API key)")
        print(" - SLSKD_API_URL (e.g., http://localhost:5030)")
        print("---")
        return

    # New check for Navidrome variables
    if not NAVIDROME_ADMIN_USER or not NAVIDROME_ADMIN_PASSWORD:
        print("---")
        logger.warning("NAVIDROME_ADMIN_USER or NAVIDROME_ADMIN_PASSWORD are not set.")
        logger.warning("Bot will run, but will NOT be able to trigger Navidrome scans.")
        print("---")

    try:
        bot.run(DISCORD_BOT_TOKEN)
    except discord.LoginFailure:
        logger.error("Failed to log in to Discord. Is your DISCORD_BOT_TOKEN correct?")
    except Exception as e:
        logger.error(f"An error occurred while running the bot: {e}")


if __name__ == "__main__":
    main()
