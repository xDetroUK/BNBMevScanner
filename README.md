🚀 PancakeSwap Front-Run Bot (BSC)
A high-frequency trading (HFT) bot that detects and exploits profitable front-running opportunities on PancakeSwap (Binance Smart Chain).

Python
Web3.py
License: MIT

🔍 Overview
This bot monitors pending transactions on BSC, identifies profitable buy orders on PancakeSwap, and calculates optimal front-running strategies using:

Gas price manipulation (priority fee bidding)

Slippage analysis (victim tolerance detection)

Constant product formula (reserve impact simulation)

⚙️ Features
Real-time transaction scanning (Web3 websocket/pending-tx filter)

Smart slippage detection (amountOutMin analysis)

Multi-DEX support (PancakeSwap-focused but extensible)

Profitability calculator (gas costs, price impact, ROI)

Sandwich attack simulation (front-run + back-run logic)

📦 Installation
bash
Copy
git clone https://github.com/yourusername/pancakeswap-frontrun-bot.git
cd pancakeswap-frontrun-bot
pip install -r requirements.txt
Requirements
Python 3.8+

Web3.py

asyncio

concurrent.futures

🛠 Configuration
Edit config.json:

json
Copy
{
  "rpc_url": "https://bsc-dataseed.binance.org/",
  "router_address": "0x10ED43C718714eb63d5aA57B78B54704E256024E",
  "gas_multiplier": 1.5,
  "max_workers": 5
}
Add your ABIs in /abis/:

routerabi.json

factoryabi.json

pairabi.json

🚦 Usage
bash
Copy
python main.py
Expected Output:
Copy
-----------------------------------------------------------------------
Transaction Hash: 0xabc...123
Swap Path: 1.0 WBNB -> 250.50 TOKEN
Price Impact: +5.25% | Slippage: 2.0%
Optimal Front-Run: 0.5 WBNB | Profit: 0.2 WBNB
📊 Strategy Logic
mermaid
Copy
sequenceDiagram
    Bot->>BSC Node: Subscribe to pending tx
    BSC Node->>Bot: New pending swap (WBNB→TOKEN)
    Bot->>Simulation: Calculate price impact
    Simulation->>Bot: 5% price increase expected
    Bot->>Strategy: Compute optimal dx (0.5 WBNB)
    Bot->>BSC: Submit tx (gas_price * 1.5)
    BSC->>Mempool: Front-run tx confirmed
    Victim->>BSC: Original swap executes
    Note right of Bot: Profit captured!
⚠️ Disclaimer
This software is for educational purposes only. Front-running may violate terms of service of exchanges and could be illegal in some jurisdictions. The developers assume no responsibility for misuse. Use at your own risk.

