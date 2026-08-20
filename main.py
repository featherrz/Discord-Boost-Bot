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
bot_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.py")
if os.path.exists(os.path.expanduser("~/Discord-Boost-Bot/.env")):
    pass
else:
    token = input("Enter your Bot Token: ")
    botName = input("Enter your Bot name (Default: HenixBot): ") or HenixBot
    with open(os.path.expanduser("~/Discord-Boost-Bot/.env"), 'w') as f:
        f.write(f"""# ---------------------------------------------------------------------------------------------------------------------------------------
# Require Variables
# ---------------------------------------------------------------------------------------------------------------------------------------

# Replace with your Bot Token
DISCORD_BOT_TOKEN=\"{token}\"

# ---------------------------------------------------------------------------------------------------------------------------------------
# Optional Variables
# ---------------------------------------------------------------------------------------------------------------------------------------

# Replace with your Bot's Name
BOT_NAME=\"{botName}\"

# Replace with your Database's File
DATABASE_FILE="bot_data.json\"""")
os.system(f'"{sys.executable}" "{bot_path}"')
