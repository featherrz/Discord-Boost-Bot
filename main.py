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
token = input("Enter your Bot Token: ")
botName = input("Enter
os.system(f'"{sys.executable}" "{bot_path}"')
