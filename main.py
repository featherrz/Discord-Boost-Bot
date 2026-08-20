import os
import time
import sys

try:
    import discord
except ModuleNotFoundError:
    print("[System]: Installing Dependencies...")

    start_time = time.perf_counter()

    os.system(f"{sys.executable} -m pip install -U discord.py")

    end_time = time.perf_counter()
    time_taken = end_time - start_time

    print(f"[System]: Installed Dependencies in {time_taken:.3f}s")


# Project directory
project_dir = os.path.dirname(os.path.abspath(__file__))

# Bot path
bot_path = os.path.join(project_dir, "bot.py")

# .env path
env_path = os.path.join(project_dir, ".env")


# Create .env if it doesn't exist
if not os.path.exists(env_path):

    token = input("Enter your Bot Token: ").strip()

    bot_name = input(
        "Enter your Bot name (Default: HenixBot): "
    ).strip() or "HenixBot"

    with open(env_path, "w") as f:
        f.write(f"""# -----------------------------------------------------------------------
# Required Variables
# -----------------------------------------------------------------------

# Replace with your Bot Token
DISCORD_BOT_TOKEN="{token}"

# -----------------------------------------------------------------------
# Optional Variables
# -----------------------------------------------------------------------

# Replace with your Bot's Name
BOT_NAME="{bot_name}"

# Replace with your Database's File
DATABASE_FILE="bot_data.json"
""")

    print("[System]: Configuration saved.")


# Start bot
os.system(f'"{sys.executable}" "{bot_path}"')
