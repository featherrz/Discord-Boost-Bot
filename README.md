# 🚀 Boost Manager    
    
A Discord bot for adding and tracking custom boosts without Nitro, with reward roles, boost history, and easy management.    
    
## ✨ Features    
- 🚀 Add custom boosts without Nitro (100% Free!)    
- 📊 Track member boost counts    
- 🎁 Reward roles for boosters    
- 📜 Boost Count history in JSON  
- 🛠️ Admin-only commands    
- 💾 Persistent boost data using JSON    
- ⚡ Fast and lightweight     
    
## 📦 Installation    
**Run:**  
```Bash  
if [ -d "/data/data/com.termux" ]; then  
    echo "[System]: Termux detected"  
      
    if ! command -v python >/dev/null 2>&1; then  
        echo "[System]: Installing Python"  
        pkg install python -y  
        echo "[System]: Installed Python"  
    else  
        echo "[System]: Python is already installed"  
    fi  
      
    PYTHON="python"  
else  
    echo "[System]: Linux detected"  
    if ! command -v python3 >/dev/null 2>&1; then  
        echo "[System]: Installing Python"  
        sudo apt update  
        sudo apt install python3 -y  
        echo "[System]: Installed Python"  
    else  
        echo "[System]: Python is already installed"  
    fi  
    PYTHON="python3"  
fi  
  
git clone https://github.com/featherrz/Discord-Boost-Bot  
cd Discord-Boost-Bot || exit 1  
  
echo "Now you can run '$PYTHON main.py' to run the bot"  
```  
**And that's it! ✅**  
  
## 📋 Commands    
| Command | Description |    
|---|---|    
| `/add-boost` | Add a boost |    
| `/remove-boost` | Remove a boost |    
| `/boosts` | View a server's boosts |    
| `/setup` | Configure boost channel, embeds, and rewards |    
| `/help` | Help Menu for Boost Bot |    
    
## 🛠️ Requirements    
- Python 3.11+    
- A Discord bot application    
- `discord.py` (Auto-installed by main.py)    
- A Discord server where you have permission to manage the bot    
  
> ⚠️ **Disclaimer:** Boost Manager uses a custom/virtual boost system. It does not create, transfer, or provide official Discord Nitro Server boosts.
