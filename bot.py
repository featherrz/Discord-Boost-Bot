"""
HenixBot - Discord Server Boost Tracker
==========================================================================================
Features:
  - Tracks total server boosts and per-user boost counts, persisted to bot_data.json
  - Real-time boost/unboost detection via on_member_update
  - Periodic safety-net re-check of every server's boost count
  - Sends a customizable embed announcement when someone boosts
  - Optional reward role for boosters
  - /boosts
  - /add-boost
  - /remove-boost
  - /help
  - /setup

Required Discord Developer Portal intents:
  - Server Members Intent
  - Message Content Intent
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

if os.path.exists(os.path.expanduser("~/Discord-Boost-Bot/.env")):
    with open(os.path.expanduser("~/Discord-Boost-Bot/.env"), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip().strip("\"'")

BOT_NAME = os.getenv("BOT_NAME")
DATA_FILE = os.getenv("DATABASE_FILE", "bot_data.json")

# Discord user IDs allowed to use /add-boost, /remove-boost, and /setup
accessUserID = [1505082327368208424]

DEFAULT_DATA = {
    "settings": {
        "bot_name": BOT_NAME,
        "channel_id": None,
        "reward_role": None,
        "embed_text": (
            "**%USER%** has boosted the server!\n"
            "The server now has **%SERVERBOOSTS%** boosts."
        ),
        "embed_color": 0x2B2D31,
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
            with open(self.file, "w", encoding="utf-8") as f:
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

            with open(self.file, "r", encoding="utf-8") as f:
                data = json.load(f)

            systemData.clear()
            systemData.update(data)

            # Make sure newer settings exist if using an old database.
            systemData.setdefault("settings", {})
            systemData["settings"].setdefault("bot_name", BOT_NAME)
            systemData["settings"].setdefault("channel_id", None)
            systemData["settings"].setdefault("reward_role", None)
            systemData["settings"].setdefault(
                "embed_text",
                DEFAULT_DATA["settings"]["embed_text"],
            )
            systemData["settings"].setdefault(
                "embed_color",
                DEFAULT_DATA["settings"]["embed_color"],
            )
            systemData.setdefault("servers", {})
            systemData.setdefault("users", {})

            return 0

        except Exception as err:
            print(f"[DATABASE] Load error: {err}")
            systemData.clear()
            systemData.update(json.loads(json.dumps(DEFAULT_DATA)))
            return 1


database = Json(DATA_FILE)
database.loadData()


# ------------------------------------------------------------------------------------
# Bot setup
# ------------------------------------------------------------------------------------

intents = discord.Intents.default()

# Required for on_member_update and premium_since detection.
intents.members = True

# NOT required anymore:
# intents.message_content = True

bot = commands.Bot(
    command_prefix=commands.when_mentioned,
    intents=intents,
)


# ------------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------------

def parse_id(raw: str) -> str:
    """
    Pull a numeric ID out of:
      <#123>
      <@123>
      <@!123>
      <@&123>

    Or return the original text.
    """
    match = re.search(r"\d{15,}", raw)
    return match.group(0) if match else raw.strip()


def to_color(value) -> int:
    """Normalize a stored color into an integer."""
    if isinstance(value, int):
        return value

    try:
        return int(str(value).lstrip("#"), 16)
    except (ValueError, TypeError):
        return 0x2B2D31


def get_user_boosts(user_id) -> int:
    user_id = str(user_id)

    if user_id not in systemData["users"]:
        systemData["users"][user_id] = {
            "boosts": 0
        }

    return systemData["users"][user_id]["boosts"]


def set_user_boosts(user_id, amount: int):
    user_id = str(user_id)

    if user_id not in systemData["users"]:
        systemData["users"][user_id] = {
            "boosts": 0
        }

    systemData["users"][user_id]["boosts"] = max(0, amount)


def ensure_server_entry(guild: discord.Guild):
    """
    Get or create this guild's tracking entry.

    boosts = real Discord boost count
    bonus  = manually credited boosts
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
    """
    Real Discord boosts + manually credited bonus boosts.
    """

    entry, _ = ensure_server_entry(guild)

    return (
        (guild.premium_subscription_count or 0)
        + entry.get("bonus", 0)
    )


def format_embed_text(text: str, member: discord.Member) -> str:
    guild = member.guild

    total_boosts = get_total_boosts(guild)
    user_boosts = get_user_boosts(member.id)

    return (
        text
        .replace("%USER%", member.display_name)
        .replace("%USERBOOSTS%", str(user_boosts))
        .replace("%SERVERLEVEL%", str(guild.premium_tier))
        .replace("%SERVERBOOSTS%", str(total_boosts))
        .replace("%TOTALBOOSTS%", str(total_boosts))
    )


async def send_boost_embed(member: discord.Member):
    channel_id = systemData["settings"].get("channel_id")

    if not channel_id:
        return

    channel = bot.get_channel(int(channel_id))

    if channel is None:
        try:
            channel = await bot.fetch_channel(int(channel_id))
        except (
            discord.NotFound,
            discord.Forbidden,
            ValueError,
        ):
            return

    text = format_embed_text(
        systemData["settings"]["embed_text"],
        member,
    )

    embed = discord.Embed(
        title="🚀 New Boost",
        description=text,
        color=to_color(
            systemData["settings"]["embed_color"]
        ),
    )

    embed.set_thumbnail(
        url=member.display_avatar.url
    )

    embed.set_footer(
        text=f"Boosted by {member} ({member.id})"
    )

    try:
        await channel.send(embed=embed)
    except discord.Forbidden:
        print(
            f"[WARN] Cannot send boost announcement "
            f"in channel {channel_id}"
        )


async def process_boost_change(guild: discord.Guild):
    guild_id = str(guild.id)

    current_boosts = guild.premium_subscription_count or 0

    entry, is_new = ensure_server_entry(guild)

    if is_new:
        database.saveData()

        print(
            f"[DATABASE] Saved initial boost count "
            f"for {guild.name}: {current_boosts}"
        )

        return

    old_boosts = entry["boosts"]

    if current_boosts == old_boosts:
        return

    difference = current_boosts - old_boosts

    entry["boosts"] = current_boosts

    database.saveData()

    if difference > 0:
        print(
            f"[BOOST] {guild.name}: "
            f"+{difference} boost(s) "
            f"({old_boosts} -> {current_boosts})"
        )
    else:
        print(
            f"[UNBOOST] {guild.name}: "
            f"{difference} boost(s) "
            f"({old_boosts} -> {current_boosts})"
        )


# ------------------------------------------------------------------------------------
# Events
# ------------------------------------------------------------------------------------

@bot.event
async def on_ready():
    os.system(
        "cls" if os.name == "nt" else "clear"
    )

    print("Registering slash commands...")

    try:
        synced = await bot.tree.sync()

        print(
            f"[COMMANDS] Synced {len(synced)} slash command(s)."
        )

    except Exception as err:
        print(
            f"[ERROR] Failed to sync slash commands: {err}"
        )

    print(
        r"""
██████╗  ██████╗  ██████╗ ███████╗████████╗    ██████╗  ██████╗ ████████╗
██╔══██╗██╔═══██╗██╔═══██╗██╔════╝╚══██╔══╝    ██╔══██╗██╔═══██╗╚══██╔══╝
██████╔╝██║   ██║██║   ██║███████╗   ██║       ██████╔╝██║   ██║   ██║
██╔══██╗██║   ██║██║   ██║╚════██║   ██║       ██╔══██╗██║   ██║   ██║
██████╔╝╚██████╔╝╚██████╔╝███████║   ██║       ██████╔╝╚██████╔╝   ██║
╚═════╝  ╚═════╝  ╚═════╝ ╚══════╝   ╚═╝       ╚═════╝  ╚═════╝    ╚═╝
"""
    )

    print(
        f"• Bot: Online (Logged in as: {bot.user})"
    )

    print("• Database: Loaded successfully")
    print("• Slash commands: Registered successfully\n")

    if not boost_checker.is_running():
        boost_checker.start()


@bot.event
async def on_member_update(
    before: discord.Member,
    after: discord.Member
):
    try:
        started_boosting = (
            before.premium_since is None
            and after.premium_since is not None
        )

        stopped_boosting = (
            before.premium_since is not None
            and after.premium_since is None
        )

        if not started_boosting and not stopped_boosting:
            return

        await process_boost_change(after.guild)

        reward_role_id = systemData["settings"].get(
            "reward_role"
        )

        role = (
            after.guild.get_role(
                int(reward_role_id)
            )
            if reward_role_id
            else None
        )

        # --------------------------------------------------------
        # STARTED BOOSTING
        # --------------------------------------------------------

        if started_boosting:

            set_user_boosts(
                after.id,
                get_user_boosts(after.id) + 1,
            )

            database.saveData()

            await send_boost_embed(after)

            if role is not None:
                try:
                    if role not in after.roles:
                        await after.add_roles(
                            role,
                            reason="Server boost reward",
                        )

                except discord.Forbidden:
                    print(
                        f"[WARN] Missing permission to add "
                        f"reward role in {after.guild.name}"
                    )

        # --------------------------------------------------------
        # STOPPED BOOSTING
        # --------------------------------------------------------

        elif stopped_boosting:

            # Only remove the role if the member has no manually
            # tracked boosts left.
            if (
                role is not None
                and role in after.roles
                and get_user_boosts(after.id) <= 0
            ):
                try:
                    await after.remove_roles(
                        role,
                        reason="No longer boosting",
                    )

                except discord.Forbidden:
                    print(
                        f"[WARN] Missing permission to remove "
                        f"reward role in {after.guild.name}"
                    )

    except Exception as err:
        print(
            f"[ERROR] Boost event: {err}"
        )


# ------------------------------------------------------------------------------------
# Periodic safety-net check
# ------------------------------------------------------------------------------------

@tasks.loop(seconds=10)
async def boost_checker():

    for guild in list(bot.guilds):

        try:
            fresh_guild = bot.get_guild(
                guild.id
            )

            if fresh_guild is not None:
                await process_boost_change(
                    fresh_guild
                )

        except Exception as err:
            print(
                f"[ERROR] Could not check boosts "
                f"for {guild.name}: {err}"
            )


@boost_checker.before_loop
async def before_boost_checker():
    await bot.wait_until_ready()


# ------------------------------------------------------------------------------------
# /boosts
# ------------------------------------------------------------------------------------

@bot.tree.command(
    name="boosts",
    description="Get the server's total boost count",
)
async def boosts(
    interaction: discord.Interaction
):

    if interaction.guild is None:
        await interaction.response.send_message(
            "This command only works in a server.",
            ephemeral=True,
        )
        return

    _, is_new = ensure_server_entry(
        interaction.guild
    )

    if is_new:
        database.saveData()

    total = get_total_boosts(
        interaction.guild
    )

    await interaction.response.send_message(
        f"🚀 **{interaction.guild.name}** "
        f"has **{total}** boosts."
    )


# ------------------------------------------------------------------------------------
# /help
# ------------------------------------------------------------------------------------

@bot.tree.command(
    name="help",
    description="Show the bot's help menu",
)
async def help_command(
    interaction: discord.Interaction
):

    embed = discord.Embed(
        title="HenixBot Help",
        description=(
            "## User Commands\n"
            "> `/boosts` — **Get server boost count**\n"
            "> `/help` — **Show this help menu**\n\n"

            "## Access-User Commands\n"
            "> `/add-boost` — **Add a boost without Nitro**\n"
            "> `/remove-boost` — **Remove a credited boost**\n"
            "> `/setup` — **Configure the bot**"
        ),
        color=0x2B2D31,
    )

    embed.set_footer(
        text="HenixBot • Slash Commands"
    )

    await interaction.response.send_message(
        embed=embed
    )


# ------------------------------------------------------------------------------------
# /add-boost
# ------------------------------------------------------------------------------------

@bot.tree.command(
    name="add-boost",
    description="Credit a user with a boost",
)
@app_commands.describe(
    user="The user to credit",
    amount="Number of boosts to add",
)
async def add_boost(
    interaction: discord.Interaction,
    user: discord.Member,
    amount: int = 1,
):

    if interaction.guild is None:
        await interaction.response.send_message(
            "This command only works in a server.",
            ephemeral=True,
        )
        return

    if interaction.user.id not in accessUserID:
        await interaction.response.send_message(
            "⛔ You don't have permission to use this command.",
            ephemeral=True,
        )
        return

    if amount <= 0:
        await interaction.response.send_message(
            "⛔ Amount must be greater than 0.",
            ephemeral=True,
        )
        return

    entry, _ = ensure_server_entry(
        interaction.guild
    )

    # Add to manually credited boosts.
    entry["bonus"] = (
        entry.get("bonus", 0) + amount
    )

    new_user_total = (
        get_user_boosts(user.id) + amount
    )

    set_user_boosts(
        user.id,
        new_user_total,
    )

    database.saveData()

    await interaction.response.send_message(
        f"🟢 **Successfully credited {amount} boost(s)** "
        f"to {user.mention}.\n"
        f"They now have **{new_user_total}** tracked boost(s).",
        ephemeral=True,
    )

    # Send same announcement as a real boost.
    await send_boost_embed(user)

    # Give reward role.
    reward_role_id = systemData["settings"].get(
        "reward_role"
    )

    if reward_role_id:

        role = interaction.guild.get_role(
            int(reward_role_id)
        )

        if role is not None and role not in user.roles:

            try:
                await user.add_roles(
                    role,
                    reason="Manually credited boost",
                )

            except discord.Forbidden:
                print(
                    f"[WARN] Missing permission to add "
                    f"reward role in {interaction.guild.name}"
                )


# ------------------------------------------------------------------------------------
# /remove-boost
# ------------------------------------------------------------------------------------

@bot.tree.command(
    name="remove-boost",
    description="Remove previously credited boosts",
)
@app_commands.describe(
    user="The user to remove boosts from",
    amount="Number of boosts to remove",
)
async def remove_boost(
    interaction: discord.Interaction,
    user: discord.Member,
    amount: int = 1,
):

    if interaction.guild is None:
        await interaction.response.send_message(
            "This command only works in a server.",
            ephemeral=True,
        )
        return

    if interaction.user.id not in accessUserID:
        await interaction.response.send_message(
            "⛔ You don't have permission to use this command.",
            ephemeral=True,
        )
        return

    if amount <= 0:
        await interaction.response.send_message(
            "⛔ Amount must be greater than 0.",
            ephemeral=True,
        )
        return

    entry, _ = ensure_server_entry(
        interaction.guild
    )

    user_boosts = get_user_boosts(
        user.id
    )

    if user_boosts <= 0:
        await interaction.response.send_message(
            "⛔ This user already has 0 boosts.",
            ephemeral=True,
        )
        return

    # Only remove manually credited boosts.
    removable = min(
        amount,
        user_boosts,
        entry.get("bonus", 0),
    )

    if removable <= 0:
        await interaction.response.send_message(
            "⛔ This user's tracked boosts came from "
            "real Nitro boosts, not manual credits, "
            "so they cannot be removed here.",
            ephemeral=True,
        )
        return

    set_user_boosts(
        user.id,
        user_boosts - removable,
    )

    entry["bonus"] = max(
        0,
        entry.get("bonus", 0) - removable,
    )

    database.saveData()

    await interaction.response.send_message(
        f"🟢 Removed **{removable}** credited boost(s) "
        f"from {user.mention}.",
        ephemeral=True,
    )

    # Remove reward role only if:
    # 1. They have no tracked boosts.
    # 2. They are not currently boosting with Nitro.
    reward_role_id = systemData["settings"].get(
        "reward_role"
    )

    if (
        reward_role_id
        and get_user_boosts(user.id) <= 0
        and user.premium_since is None
    ):

        role = interaction.guild.get_role(
            int(reward_role_id)
        )

        if role is not None and role in user.roles:

            try:
                await user.remove_roles(
                    role,
                    reason="Credited boosts removed",
                )

            except discord.Forbidden:
                print(
                    f"[WARN] Missing permission to remove "
                    f"reward role in {interaction.guild.name}"
                )


# ------------------------------------------------------------------------------------
# Setup Yes/No buttons
# ------------------------------------------------------------------------------------

class YesNoView(discord.ui.View):

    def __init__(
        self,
        author_id: int,
        timeout: float = 60,
    ):
        super().__init__(timeout=timeout)

        self.author_id = author_id
        self.value = None

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:

        if interaction.user.id != self.author_id:

            await interaction.response.send_message(
                "This isn't your setup session.",
                ephemeral=True,
            )

            return False

        return True

    @discord.ui.button(
        label="Yes",
        style=discord.ButtonStyle.success,
    )
    async def yes(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        self.value = True

        await interaction.response.defer()

        self.stop()

    @discord.ui.button(
        label="No",
        style=discord.ButtonStyle.danger,
    )
    async def no(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        self.value = False

        await interaction.response.defer()

        self.stop()


# ------------------------------------------------------------------------------------
# /setup
# ------------------------------------------------------------------------------------

@bot.tree.command(
    name="setup",
    description="Configure the boost tracker",
)
async def setup(
    interaction: discord.Interaction
):

    if interaction.guild is None:
        await interaction.response.send_message(
            "This command only works in a server.",
            ephemeral=True,
        )
        return

    if interaction.user.id not in accessUserID:
        await interaction.response.send_message(
            "⛔ You don't have permission to use this command.",
            ephemeral=True,
        )
        return

    # Immediately acknowledge the slash command.
    await interaction.response.defer()

    guild = interaction.guild

    # ------------------------------------------------------------------------
    # Message checker
    # ------------------------------------------------------------------------

    def check(message: discord.Message) -> bool:

        return (
            message.author.id == interaction.user.id
            and message.channel.id == interaction.channel_id
        )

    async def get_reply(timeout: int = 120):

        try:
            return await bot.wait_for(
                "message",
                check=check,
                timeout=timeout,
            )

        except asyncio.TimeoutError:

            await interaction.followup.send(
                "⏱️ Setup timed out."
            )

            return None

    # ------------------------------------------------------------------------
    # Announcement channel
    # ------------------------------------------------------------------------

    await interaction.followup.send(
        "Enter the channel name, ID, or mention "
        "for boost announcements (`Q` to skip):"
    )

    msg = await get_reply()

    if msg is not None:

        if msg.content.strip().lower() != "q":

            raw = msg.content.strip()

            channel_id = parse_id(raw)

            if channel_id.isdigit():

                channel = guild.get_channel(
                    int(channel_id)
                )

            else:

                channel = discord.utils.get(
                    guild.text_channels,
                    name=raw,
                )

            if channel:

                systemData["settings"]["channel_id"] = str(
                    channel.id
                )

                database.saveData()

                await interaction.followup.send(
                    f"✅ Boost announcements will be sent "
                    f"in {channel.mention}"
                )

            else:

                await interaction.followup.send(
                    "⛔ Couldn't find that channel, skipping."
                )

    # ------------------------------------------------------------------------
    # Reward role
    # ------------------------------------------------------------------------

    view = YesNoView(
        interaction.user.id
    )

    await interaction.followup.send(
        "Do you want to set up a reward role for boosters?",
        view=view,
    )

    await view.wait()

    if view.value:

        await interaction.followup.send(
            "Enter the role name, ID, or mention "
            "(`Q` to skip):"
        )

        msg = await get_reply()

        if msg is not None:

            if msg.content.strip().lower() != "q":

                raw = msg.content.strip()

                role_id = parse_id(raw)

                if role_id.isdigit():

                    role = guild.get_role(
                        int(role_id)
                    )

                else:

                    role = discord.utils.get(
                        guild.roles,
                        name=raw,
                    )

                if role:

                    systemData["settings"]["reward_role"] = str(
                        role.id
                    )

                    database.saveData()

                    await interaction.followup.send(
                        f"✅ {role.mention} set as the "
                        f"boosting reward role"
                    )

                else:

                    await interaction.followup.send(
                        "⛔ Couldn't find that role, skipping."
                    )

    # ------------------------------------------------------------------------
    # Embed text
    # ------------------------------------------------------------------------

    current_embed = discord.Embed(
        title="Current Embed Text",
        description=(
            f"> {systemData['settings']['embed_text']}\n\n"
            "## Placeholders\n"
            "> **%USER%** — boosting user's name\n"
            "> **%USERBOOSTS%** — user's total boosts\n"
            "> **%SERVERLEVEL%** — server boost level\n"
            "> **%SERVERBOOSTS%** — server total boosts\n"
            "> **%TOTALBOOSTS%** — alias for server total boosts"
        ),
        color=to_color(
            systemData["settings"]["embed_color"]
        ),
    )

    await interaction.followup.send(
        embed=current_embed
    )

    view = YesNoView(
        interaction.user.id
    )

    await interaction.followup.send(
        "Do you want to change the embed text?",
        view=view,
    )

    await view.wait()

    if view.value:

        await interaction.followup.send(
            "Enter the new embed text (`Q` to cancel):"
        )

        msg = await get_reply(
            timeout=180
        )

        if msg is not None:

            if msg.content.strip().lower() != "q":

                systemData["settings"]["embed_text"] = (
                    msg.content
                )

                database.saveData()

                await interaction.followup.send(
                    "✅ Embed text updated."
                )

    # ------------------------------------------------------------------------
    # Embed color
    # ------------------------------------------------------------------------

    current_color = discord.Embed(
        title="Current Embed Color",
        description=(
            f"> **#{to_color(systemData['settings']['embed_color']):06X}**"
        ),
        color=to_color(
            systemData["settings"]["embed_color"]
        ),
    )

    await interaction.followup.send(
        embed=current_color
    )

    view = YesNoView(
        interaction.user.id
    )

    await interaction.followup.send(
        "Do you want to change the embed color?",
        view=view,
    )

    await view.wait()

    if view.value:

        await interaction.followup.send(
            "Enter a hex color for the embed "
            "(example: `#0055FF`), or `Q` to cancel."
        )

        msg = await get_reply(
            timeout=180
        )

        if msg is not None:

            if msg.content.strip().lower() != "q":

                try:

                    color_value = int(
                        msg.content.strip().lstrip("#"),
                        16,
                    )

                    if not 0 <= color_value <= 0xFFFFFF:
                        raise ValueError

                    systemData["settings"]["embed_color"] = (
                        color_value
                    )

                    database.saveData()

                    await interaction.followup.send(
                        "✅ Embed color updated."
                    )

                except ValueError:

                    await interaction.followup.send(
                        "⛔ That's not a valid hex color, skipping."
                    )

    # ------------------------------------------------------------------------
    # Finished
    # ------------------------------------------------------------------------

    await interaction.followup.send(
        "✅ **Setup complete!**"
    )


# ------------------------------------------------------------------------------------
# Run
# ------------------------------------------------------------------------------------

class TokenNotFound(Exception):
    pass


if __name__ == "__main__":

    BOT_TOKEN = os.getenv(
        "DISCORD_BOT_TOKEN"
    )

    if not BOT_TOKEN:
        raise TokenNotFound(
            "Token not found in .env"
        )

    bot.run(BOT_TOKEN)
