"""
HenixBot - Discord Server Boost Tracker
==========================================================================================
Features:
  - Tracks total server boosts and per-user boost counts, persisted to bot_data.json
  - Real-time boost/unboost detection via on_member_update
  - Periodic safety-net re-check of every server's boost count (boost_checker loop)
  - Sends a customizable embed announcement when someone boosts, with placeholders:
        %USER%          -> the booster's display name
        %USERBOOSTS%    -> that user's total tracked boosts
        %SERVERLEVEL%   -> the server's current boost (Nitro) tier
        %SERVERBOOSTS%  -> the server's total boost count
  - Optional reward role, automatically given while a member is boosting and
    removed when they stop
  - /boosts        - anyone can check the server's current boost count
  - /add-boost     - access users can manually credit someone with boosts
  - /remove-boost  - access users can manually remove boosts from someone
  - !help          - shows a help menu
  - !setup         - interactive wizard (access users only) to configure the
                      announcement channel, reward role, embed text, and embed color

Setup:
  1. pip install -U discord.py
  2. Put your bot token in BOT_TOKEN below (or set the DISCORD_BOT_TOKEN env var)
  3. In the Discord Developer Portal, enable "Server Members Intent" and
     "Message Content Intent" for your bot
  4. Add your own Discord user ID (as an int) to accessUserID below so you can
     use /add-boost, /remove-boost, and !setup
==========================================================================================
"""

import asyncio
import json
import os
import re

import discord
from discord import app_commands
from discord.ext import commands, tasks

# ------------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------------
if os.path.exists(".env"):
    with open(".env") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip().strip('"\'')

BOT_NAME = os.getenv("BOT_NAME")
DATA_FILE = os.getenv("DATABASE_FILE")

# Discord user IDs (as integers) allowed to use /add-boost, /remove-boost, and !setup
accessUserID = [1505082327368208424]

DEFAULT_DATA = {
    "prefixs": ["."],
    "settings": {
        "bot_name": BOT_NAME,
        "channel_id": None,
        "reward_role": None,
        "embed_text": (
            "**%USER%** has boosted the server!\n"
            "The server now has **%SERVERBOOSTS%** boosts."
        ),
        "embed_color": 0x2b2d31,
    },
    "servers": {},
    "users": {},
}

systemData = {}


# ------------------------------------------------------------------------------------
# Persistence
# ------------------------------------------------------------------------------------

class Json:
    def __init__(self, file):
        self.file = file

    def saveData(self):
        try:
            with open(self.file, "w") as f:
                json.dump(systemData, f, indent=4)
            return 0
        except Exception as err:
            print(f"[DATABASE] Save error: {err}")
            return 1

    def loadData(self):
        try:
            if not os.path.exists(self.file):
                systemData.clear()
                systemData.update(json.loads(json.dumps(DEFAULT_DATA)))
                self.saveData()
                return 0

            with open(self.file, "r") as f:
                data = json.load(f)

            systemData.clear()
            systemData.update(data)
            return 0
        except Exception as err:
            print(f"[DATABASE] Load error: {err}")
            systemData.clear()
            systemData.update(json.loads(json.dumps(DEFAULT_DATA)))
            return 1


database = Json(DATA_FILE)
database.loadData()  # load BEFORE the bot is created so the prefix list is correct


# ------------------------------------------------------------------------------------
# Bot setup
# ------------------------------------------------------------------------------------

intents = discord.Intents.default()
intents.members = True          # privileged - required for on_member_update
intents.message_content = True  # privileged - required for prefix commands

bot = commands.Bot(
    command_prefix=systemData["prefixs"],
    intents=intents,
    help_command=None,  # replaced by our own !help below
)


# ------------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------------

def parse_id(raw: str) -> str:
    """Pull a numeric ID out of a mention like <#123>, <@123>, <@!123>, <@&123>,
    or just return the raw text (e.g. a plain ID or a channel/role name)."""
    match = re.search(r"\d{15,}", raw)
    return match.group(0) if match else raw.strip()


def to_color(value) -> int:
    """Normalize a stored color (int or hex string) into an int for discord.Embed."""
    if isinstance(value, int):
        return value
    try:
        return int(str(value).lstrip("#"), 16)
    except (ValueError, TypeError):
        return 0x2b2d31


def get_user_boosts(user_id) -> int:
    user_id = str(user_id)
    if user_id not in systemData["users"]:
        systemData["users"][user_id] = {"boosts": 0}
    return systemData["users"][user_id]["boosts"]


def set_user_boosts(user_id, amount: int):
    user_id = str(user_id)
    if user_id not in systemData["users"]:
        systemData["users"][user_id] = {"boosts": 0}
    systemData["users"][user_id]["boosts"] = max(0, amount)


def ensure_server_entry(guild: discord.Guild):
    """Get (creating if needed) this guild's tracking entry.

    'boosts' mirrors Discord's real premium_subscription_count (kept in sync by
    process_boost_change). 'bonus' is boosts manually credited via /add-boost
    that don't come from Discord, so the polling loop never overwrites them.
    Returns (entry, was_just_created).
    """
    guild_id = str(guild.id)
    is_new = guild_id not in systemData["servers"]
    if is_new:
        systemData["servers"][guild_id] = {
            "boosts": guild.premium_subscription_count or 0,
            "bonus": 0,
        }
    else:
        systemData["servers"][guild_id].setdefault("bonus", 0)
    return systemData["servers"][guild_id], is_new


def get_total_boosts(guild: discord.Guild) -> int:
    """Real Discord boosts + manually credited bonus boosts."""
    entry, _ = ensure_server_entry(guild)
    return (guild.premium_subscription_count or 0) + entry.get("bonus", 0)


def format_embed_text(text: str, member: discord.Member) -> str:
    guild = member.guild
    total_boosts = get_total_boosts(guild)
    user_boosts = get_user_boosts(member.id)

    return (
        text.replace("%USER%", member.display_name)
            .replace("%USERBOOSTS%", str(user_boosts))
            .replace("%SERVERLEVEL%", str(guild.premium_tier))
            .replace("%SERVERBOOSTS%", str(total_boosts))
            .replace("%TOTALBOOSTS%", str(total_boosts))  # legacy alias
    )


async def send_boost_embed(member: discord.Member):
    channel_id = systemData["settings"].get("channel_id")
    if not channel_id:
        return

    channel = bot.get_channel(int(channel_id))
    if channel is None:
        try:
            channel = await bot.fetch_channel(int(channel_id))
        except (discord.NotFound, discord.Forbidden, ValueError):
            return

    text = format_embed_text(systemData["settings"]["embed_text"], member)
    embed = discord.Embed(
        title="\U0001F680 New Boost",
        description=text,
        color=to_color(systemData["settings"]["embed_color"]),
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text=f"Boosted by {member} ({member.id})")

    await channel.send(embed=embed)


async def process_boost_change(guild: discord.Guild):
    guild_id = str(guild.id)
    current_boosts = guild.premium_subscription_count or 0
    entry, is_new = ensure_server_entry(guild)

    if is_new:
        database.saveData()
        print(f"[DATABASE] Saved initial boost count for {guild.name}: {current_boosts}")
        return

    old_boosts = entry["boosts"]
    if current_boosts == old_boosts:
        return

    difference = current_boosts - old_boosts
    entry["boosts"] = current_boosts
    database.saveData()

    if difference > 0:
        print(f"[BOOST] {guild.name}: +{difference} boost(s) ({old_boosts} -> {current_boosts})")
    else:
        print(f"[UNBOOST] {guild.name}: {difference} boost(s) ({old_boosts} -> {current_boosts})")


# ------------------------------------------------------------------------------------
# Events
# ------------------------------------------------------------------------------------

@bot.event
async def on_ready():
    os.system("cls" if os.name == "nt" else "clear")
    print("Registering commands...")
    try:
        await bot.tree.sync()
    except Exception as err:
        print(f"[ERROR] Failed to sync slash commands: {err}")

    print(r"""
██████╗  ██████╗  ██████╗ ███████╗████████╗    ██████╗  ██████╗ ████████╗
██╔══██╗██╔═══██╗██╔═══██╗██╔════╝╚══██╔══╝    ██╔══██╗██╔═══██╗╚══██╔══╝
██████╔╝██║   ██║██║   ██║███████╗   ██║       ██████╔╝██║   ██║   ██║
██╔══██╗██║   ██║██║   ██║╚════██║   ██║       ██╔══██╗██║   ██║   ██║
██████╔╝╚██████╔╝╚██████╔╝███████║   ██║       ██████╔╝╚██████╔╝   ██║
╚═════╝  ╚═════╝  ╚═════╝ ╚══════╝   ╚═╝       ╚═════╝  ╚═════╝    ╚═╝
""")
    print(f"\u2022 Bot: Online (Logged in as: {bot.user})")
    print("\u2022 Database: Loaded successfully")
    print("\u2022 Slash commands: Registered successfully\n")
    boost_checker.start()


@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    try:
        started_boosting = before.premium_since is None and after.premium_since is not None
        stopped_boosting = before.premium_since is not None and after.premium_since is None

        if not started_boosting and not stopped_boosting:
            return

        await process_boost_change(after.guild)

        reward_role_id = systemData["settings"].get("reward_role")
        role = after.guild.get_role(int(reward_role_id)) if reward_role_id else None

        if started_boosting:
            set_user_boosts(after.id, get_user_boosts(after.id) + 1)
            database.saveData()
            await send_boost_embed(after)

            if role is not None:
                try:
                    await after.add_roles(role, reason="Server boost reward")
                except discord.Forbidden:
                    print(f"[WARN] Missing permission to add reward role in {after.guild.name}")

        elif stopped_boosting:
            if role is not None and role in after.roles:
                try:
                    await after.remove_roles(role, reason="No longer boosting")
                except discord.Forbidden:
                    print(f"[WARN] Missing permission to remove reward role in {after.guild.name}")

    except Exception as err:
        print(f"[ERROR] Boost event: {err}")


# ------------------------------------------------------------------------------------
# Periodic safety-net check
# ------------------------------------------------------------------------------------

@tasks.loop(seconds=10)
async def boost_checker():
    for guild in list(bot.guilds):
        try:
            # bot.get_guild reads from the gateway cache (kept fresh automatically by
            # Discord's GUILD_UPDATE events) instead of making an API call every
            # 10 seconds, which avoids rate limits. guild.fetch() does not exist.
            fresh_guild = bot.get_guild(guild.id)
            if fresh_guild is not None:
                await process_boost_change(fresh_guild)
        except Exception as err:
            print(f"[ERROR] Could not check boosts for {guild.name}: {err}")


@boost_checker.before_loop
async def before_boost_checker():
    await bot.wait_until_ready()


# ------------------------------------------------------------------------------------
# Slash commands
# ------------------------------------------------------------------------------------

@bot.tree.command(name="boosts", description="Get total server boosts")
async def boosts(i: discord.Interaction):
    if i.guild is None:
        await i.response.send_message("This command only works in a server.", ephemeral=True)
        return

    _, is_new = ensure_server_entry(i.guild)
    if is_new:
        database.saveData()

    total = get_total_boosts(i.guild)
    await i.response.send_message(f"\U0001F680 **{i.guild.name}** has **{total}** boosts.")


@bot.tree.command(name="add-boost", description="Credit a user with a boost, exactly like a real one (access users only)")
@app_commands.describe(user="The user to credit", amount="Number of boosts to add")
async def add_boost(i: discord.Interaction, user: discord.Member, amount: int = 1):
    if i.guild is None:
        await i.response.send_message("This command only works in a server.", ephemeral=True)
        return
    if i.user.id not in accessUserID:
        await i.response.send_message("\u26D4 You don't have permission to use this command.", ephemeral=True)
        return
    if amount <= 0:
        await i.response.send_message("\u26D4 Amount must be greater than 0.", ephemeral=True)
        return

    # Credited to a separate "bonus" pool rather than the real Discord boost count,
    # so the periodic sync (which trusts Discord as ground truth) never wipes it out.
    entry, _ = ensure_server_entry(i.guild)
    entry["bonus"] = entry.get("bonus", 0) + amount

    new_user_total = get_user_boosts(user.id) + amount
    set_user_boosts(user.id, new_user_total)
    database.saveData()

    await i.response.send_message(
        f"\U0001F7E2 **Successfully**: Credited {amount} boost(s) to {user.mention} "
        f"(now {new_user_total} total). Announcing it now...",
        ephemeral=True,
    )

    # Fire the exact same announcement embed a real boost would trigger.
    await send_boost_embed(user)

    # Apply the reward role, same as a real boost would.
    reward_role_id = systemData["settings"].get("reward_role")
    if reward_role_id:
        role = i.guild.get_role(int(reward_role_id))
        if role is not None and role not in user.roles:
            try:
                await user.add_roles(role, reason="Manually credited boost")
            except discord.Forbidden:
                print(f"[WARN] Missing permission to add reward role in {i.guild.name}")


@bot.tree.command(name="remove-boost", description="Remove previously credited boosts from a user (access users only)")
@app_commands.describe(user="The user to remove boosts from", amount="Number of boosts to remove")
async def remove_boost(i: discord.Interaction, user: discord.Member, amount: int = 1):
    if i.guild is None:
        await i.response.send_message("This command only works in a server.", ephemeral=True)
        return
    if i.user.id not in accessUserID:
        await i.response.send_message("\u26D4 You don't have permission to use this command.", ephemeral=True)
        return
    if amount <= 0:
        await i.response.send_message("\u26D4 Amount must be greater than 0.", ephemeral=True)
        return

    entry, _ = ensure_server_entry(i.guild)
    user_boosts = get_user_boosts(user.id)

    if user_boosts <= 0:
        await i.response.send_message("\u26D4 **Error**: This user already has 0 boosts.", ephemeral=True)
        return

    # Only ever pull from manually credited "bonus" boosts - real Nitro boosts
    # come from Discord itself and can't be revoked by the bot.
    removable = min(amount, user_boosts, entry.get("bonus", 0))
    if removable <= 0:
        await i.response.send_message(
            "\u26D4 **Error**: This user's boosts came from a real Nitro boost, not a credit, "
            "so they can't be removed here.",
            ephemeral=True,
        )
        return

    set_user_boosts(user.id, user_boosts - removable)
    entry["bonus"] = max(0, entry.get("bonus", 0) - removable)
    database.saveData()

    await i.response.send_message(
        f"\U0001F7E2 **Successfully**: Removed {removable} credited boost(s) from {user.mention}",
        ephemeral=True,
    )

    # If they have no boosts left at all (credited or real), take back the reward role.
    reward_role_id = systemData["settings"].get("reward_role")
    if reward_role_id and get_user_boosts(user.id) <= 0 and user.premium_since is None:
        role = i.guild.get_role(int(reward_role_id))
        if role is not None and role in user.roles:
            try:
                await user.remove_roles(role, reason="Credited boosts removed")
            except discord.Forbidden:
                print(f"[WARN] Missing permission to remove reward role in {i.guild.name}")


# ------------------------------------------------------------------------------------
# Prefix commands
# ------------------------------------------------------------------------------------

@bot.command(name="help")
async def help_command(ctx: commands.Context):
    prefix = systemData["prefixs"][0] if systemData["prefixs"] else "!"
    embed = discord.Embed(
        description=(
            "# Help Menu\n"
            f"**Prefix**: `{prefix}` | **Mention**: {bot.user.mention}\n"
            "A list of commands and their uses\n\n"
            "## User Commands\n"
            "> - `/boosts` \u2014 **Get server boosts count**\n"
            f"> - `{prefix}help` \u2014 **Show list of commands**\n\n"
            "## Access-User Commands\n"
            "> - `/add-boost` \u2014 **Add a boost without Nitro**\n"
            "> - `/remove-boost` \u2014 **Remove a boost without Nitro**\n"
            f"> - `{prefix}setup` \u2014 **Configure the bot**"
        ),
        color=0x2b2d31,
    )
    await ctx.send(embed=embed)


class YesNoView(discord.ui.View):
    def __init__(self, author_id: int, timeout: float = 60):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.value = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This isn't your setup session.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.success)
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="No", style=discord.ButtonStyle.danger)
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        await interaction.response.defer()
        self.stop()


@bot.command(name="setup")
async def setup(ctx: commands.Context):
    if ctx.author.id not in accessUserID:
        await ctx.send("\u26D4 You don't have permission to use this command.")
        return

    def check(message: discord.Message) -> bool:
        return message.author.id == ctx.author.id and message.channel == ctx.channel

    async def get_reply(timeout: int = 120):
        try:
            return await bot.wait_for("message", check=check, timeout=timeout)
        except asyncio.TimeoutError:
            await ctx.send("\u23F1\uFE0F Timed out.")
            return None

    # --- Announcement channel -------------------------------------------------
    await ctx.send("Enter the channel name, ID, or mention for boost announcements (`Q` to skip):")
    msg = await get_reply()
    if msg and msg.content.strip().lower() != "q":
        raw = msg.content.strip()
        channel_id = parse_id(raw)
        channel = (
            ctx.guild.get_channel(int(channel_id)) if channel_id.isdigit()
            else discord.utils.get(ctx.guild.text_channels, name=raw)
        )
        if channel:
            systemData["settings"]["channel_id"] = str(channel.id)
            database.saveData()
            await ctx.send(f"\u2705 Boost announcements will be sent in {channel.mention}")
        else:
            await ctx.send("\u26D4 Couldn't find that channel, skipping.")

    # --- Reward role ------------------------------------------------------------
    view = YesNoView(ctx.author.id)
    await ctx.send("Do you want to set up a reward role for boosters?", view=view)
    await view.wait()
    if view.value:
        await ctx.send("Enter the role name, ID, or mention (`Q` to skip):")
        msg = await get_reply()
        if msg and msg.content.strip().lower() != "q":
            raw = msg.content.strip()
            role_id = parse_id(raw)
            role = (
                ctx.guild.get_role(int(role_id)) if role_id.isdigit()
                else discord.utils.get(ctx.guild.roles, name=raw)
            )
            if role:
                systemData["settings"]["reward_role"] = str(role.id)
                database.saveData()
                await ctx.send(f"\u2705 {role.mention} set as the boosting reward role")
            else:
                await ctx.send("\u26D4 Couldn't find that role, skipping.")

    # --- Embed text ---------------------------------------------------------
    embed = discord.Embed(
        title="Current Embed Text",
        description=(
            f"> {systemData['settings']['embed_text']}\n\n"
            "## Placeholders\n"
            "> - **%USER%** \u2014 the boosting user's name\n"
            "> - **%USERBOOSTS%** \u2014 the user's total boosts\n"
            "> - **%SERVERLEVEL%** \u2014 the server's boost level\n"
            "> - **%SERVERBOOSTS%** \u2014 the server's total boosts"
        ),
        color=to_color(systemData["settings"]["embed_color"]),
    )
    await ctx.send(embed=embed)
    view = YesNoView(ctx.author.id)
    await ctx.send("Do you want to change the embed text?", view=view)
    await view.wait()
    if view.value:
        await ctx.send("Enter the new embed text (`Q` to cancel):")
        msg = await get_reply(timeout=180)
        if msg and msg.content.strip().lower() != "q":
            systemData["settings"]["embed_text"] = msg.content
            database.saveData()
            await ctx.send("\u2705 Embed text updated.")

    # --- Embed color ---------------------------------------------------------
    embed = discord.Embed(
        title="Current Embed Color",
        description=f"> **#{to_color(systemData['settings']['embed_color']):06X}**",
        color=to_color(systemData["settings"]["embed_color"]),
    )
    await ctx.send(embed=embed)
    view = YesNoView(ctx.author.id)
    await ctx.send("Do you want to change the embed color?", view=view)
    await view.wait()
    if view.value:
        await ctx.send(
            "Enter a hex color for the embed (e.g. `#0055FF`), or `Q` to cancel:\n\n"
            "**How to get a hex color:**\n"
            "> 1. Go to <https://htmlcolorcodes.com/color-picker/>\n"
            "> 2. Choose your color and copy the hex code (e.g. `#0055FF`)\n"
            "> 3. Paste it here"
        )
        msg = await get_reply(timeout=180)
        if msg and msg.content.strip().lower() != "q":
            try:
                color_value = int(msg.content.strip().lstrip("#"), 16)
                systemData["settings"]["embed_color"] = color_value
                database.saveData()
                await ctx.send("\u2705 Embed color updated.")
            except ValueError:
                await ctx.send("\u26D4 That's not a valid hex color, skipping.")

    await ctx.send("\u2705 **Setup complete!**")


# ------------------------------------------------------------------------------------
# Run
# ------------------------------------------------------------------------------------
class TokenNotFound(Exception):
    pass

if __name__ == "__main__":
    BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    if not BOT_TOKEN:
        raise TokenNotFound("Token not found in .env")
    bot.run(BOT_TOKEN)

