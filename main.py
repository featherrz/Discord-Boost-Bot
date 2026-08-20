import os, time, sys

try:
    import discord
except ModuleNotFoundError:
    print("[System]: Installing Dependencies...")    
    start_time = time.perf_counter()    
    os.system(f"{sys.executable} -m pip install -U discord.py")    
    end_time = time.perf_counter()    
    time_taken = end_time - start_time   
    print(f"[System]: Installed Dependencies in {time_taken:.3f}s")
  
os.system(f"{sys.executable} bot.py")
