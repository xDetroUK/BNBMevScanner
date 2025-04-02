import json
import asyncio
import logging
from web3 import Web3
from web3.exceptions import Web3RPCError
from concurrent.futures import ThreadPoolExecutor


# Disable logging for web3 to suppress any internal warnings/errors it may output
logging.getLogger("web3").setLevel(logging.CRITICAL)
ABI_FILE_PATH = "/root/binance/scripts/vscode/config/workspace/pyTest/abis/routerabi.json"
FACTORY_ABI_PATH = "/root/binance/scripts/vscode/config/workspace/pyTest/abis/factoryabi.json"
PAIR_ABI_PATH = "/root/binance/scripts/vscode/config/workspace/pyTest/abis/pairabi.json"

with open(ABI_FILE_PATH, "r") as file:
    pcsAbi = json.loads(file.read())
# Constants
WBNB_TOKEN = Web3.to_checksum_address("0xBB4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c")
USDT_TOKEN = Web3.to_checksum_address("0x55d398326f99059fF775485246999027B3197955")


# Known token decimals for BNB and common tokens
KNOWN_TOKEN_DECIMALS = {
    WBNB_TOKEN: 18,
    USDT_TOKEN: 18,
}

# Factory and Pair ABIs
with open(FACTORY_ABI_PATH, "r") as file:
    FACTORY_ABI = json.load(file)

with open(PAIR_ABI_PATH, "r") as file:
    PAIR_ABI = json.load(file)

# HTTP URL
def get_http_url() -> str:
    return "http://localhost:8545"  # Adjust this URL to match your node's HTTP endpoint

# Initialize Web3 connection using HTTP Provider
web3 = Web3(Web3.HTTPProvider(get_http_url()))
print("Web3 connected:", web3.is_connected())


pcsRouter = web3.to_checksum_address("0x10ED43C718714eb63d5aA57B78B54704E256024E")
pcsContract = web3.eth.contract(address=pcsRouter, abi=pcsAbi)

# Define additional DEXes with their Router addresses and ABIs
DEXES = [
    {
        "name": "PancakeSwap",
        "router_address": "0x10ED43C718714eb63d5aA57B78B54704E256024E",
        "factory_address": "0xca143ce32fe78f1f7019d7d551a6402fc5350c73",
        "router_abi": pcsAbi,  # Assuming same ABI as PancakeSwap
        "factory_abi": FACTORY_ABI
    },

]

# Initialize contracts for each DEX
for dex in DEXES:
    dex["router_address"] = web3.to_checksum_address(dex["router_address"])
    dex["factory_address"] = web3.to_checksum_address(dex["factory_address"])
    
    dex["router_contract"] = web3.eth.contract(address=dex["router_address"], abi=dex["router_abi"])
    dex["factory_contract"] = web3.eth.contract(address=dex["factory_address"], abi=dex["factory_abi"])

# Function to get token symbol and decimals from the contract
def get_token_details(token_address):
    try:
        if token_address in KNOWN_TOKEN_DECIMALS:
            decimals = KNOWN_TOKEN_DECIMALS[token_address]
            token_contract = web3.eth.contract(address=token_address, abi=[
                {"constant": True, "inputs": [], "name": "symbol", "outputs": [{"name": "", "type": "string"}], "type": "function"}
            ])
            symbol = token_contract.functions.symbol().call()
            return symbol, decimals

        token_contract = web3.eth.contract(address=token_address, abi=[
            {"constant": True, "inputs": [], "name": "symbol", "outputs": [{"name": "", "type": "string"}], "type": "function"},
            {"constant": True, "inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "type": "function"}
        ])
        symbol = token_contract.functions.symbol().call()
        decimals = token_contract.functions.decimals().call()
        
        # Validate decimals
        if not (0 <= decimals <= 30):
            decimals = 18
        
        # Update KNOWN_TOKEN_DECIMALS dynamically
        KNOWN_TOKEN_DECIMALS[token_address] = decimals
        
        return symbol, decimals
    except Exception as e:
        print(f"====================================D")
        return "Unknown", 18

# Helper function to format amounts
def format_amount(amount):
    """
    Formats the amount based on its magnitude and removes unnecessary trailing zeros.

    :param amount: The adjusted amount to format.
    :return: A string representation of the formatted amount.
    """
    if amount >= 1:
        # Format with up to 4 decimal places for amounts >= 1
        formatted = f"{amount:.4f}"
    elif amount >= 1e-6:
        # Format with up to 8 decimal places for amounts between 1e-6 and 1
        formatted = f"{amount:.8f}"
    elif amount >= 1e-12:
        # Format with up to 14 decimal places for amounts between 1e-12 and 1e-6
        formatted = f"{amount:.14f}"
    else:
        # For amounts smaller than 1e-12, format with up to 18 decimal places
        formatted = f"{amount:.18f}"

    # Remove trailing zeros and the decimal point if not needed
    if '.' in formatted:
        formatted = formatted.rstrip('0').rstrip('.')
    return formatted

# Function to calculate amounts for each step in the swap path
def get_swap_amounts(amount_in, path):
    try:
        # Using PancakeSwap Router to fetch amounts
        amounts = pcsContract.functions.getAmountsOut(amount_in, path).call()
        return amounts
    except Exception as e:
        return None

def is_buy_order(path):
    """
    Checks if the transaction is a buy order.
    A buy order swaps from base tokens (WBNB, USDT) into another token.
    """
    # Define base tokens (e.g., WBNB and USDT)
    base_tokens = {WBNB_TOKEN}

    # A valid buy order must:
    # - Start with a base token
    # - End with a non-base token
    if len(path) >= 2 and path[0] in base_tokens and path[-1] not in base_tokens:
        return True
    return False

def calculate_frontrun_gas_price(victim_gas_price, overpayment_percentage=0.3):
    """
    Calculate the gas price to overpay for front-running.

    :param victim_gas_price: The gas price used by the victim's transaction.
    :param overpayment_percentage: The percentage by which to overpay (e.g., 0.2 for 20%).
    :return: The gas price to set for the front-running transaction.
    """
    if victim_gas_price <= 0 or overpayment_percentage <= 0:
        raise ValueError("Invalid gas price or overpayment percentage")

    return int(victim_gas_price * (1 + overpayment_percentage))



def calculate_slippage(amount_in, amount_out_min, path):
    """
    Calculate the slippage tolerance the victim has set for their transaction.

    :param amount_in: The input token amount for the victim's trade.
    :param amount_out_min: The minimum amount of tokens the victim expects (set in their transaction).
    :param path: The swap path for the victim's trade.
    :return: The victim's slippage tolerance as a percentage.
    """
    try:
        # Fetch the expected output for the given input and path
        expected_amounts = pcsContract.functions.getAmountsOut(amount_in, path).call()
        if not expected_amounts or len(expected_amounts) < 2:
            return None

        # The expected amount of output tokens
        expected_output = expected_amounts[-1]

        # Calculate victim's slippage tolerance
        victim_slippage_tolerance = ((expected_output - amount_out_min) / expected_output) * 100

        return max(0, victim_slippage_tolerance)  # Ensure no negative slippage
    except Exception as e:
        print(f"Error calculating victim's slippage: {e}")
        return None

def calculate_optimal_dx(victim_input, min_tokens_out, reserve_x, reserve_y, dex_fee):
    """
    Calculate the optimal input amount (dx) for front-running based on the victim's trade parameters and pool reserves.

    :param victim_input: The input amount of tokens for the victim's trade.
    :param min_tokens_out: The minimum tokens out the victim expects (their slippage tolerance).
    :param reserve_x: The current reserve of the base token in the pool.
    :param reserve_y: The current reserve of the target token in the pool.
    :param dex_fee: The DEX fee multiplier (e.g., 0.9975 for 0.25% fee).
    :return: The optimal input amount (dx) for front-running or None if conditions are invalid.
    """
    try:
        # Validate inputs
        if min_tokens_out <= 0 or victim_input <= 0 or reserve_x <= 0 or reserve_y <= 0 or dex_fee <= 0:
            return None

        # Calculate price impact of victim's trade
        effective_price = reserve_y / reserve_x
        victim_price = victim_input / min_tokens_out

        if victim_price >= effective_price:
            # Victim's expected price is already unfavorable, front-running not viable
            return None

        # Calculate denominator: how the victim's trade affects pool reserves
        denominator = (reserve_y / min_tokens_out) * dex_fee - 1

        if denominator <= 0:
            # Denominator invalid, cannot calculate dx
            return None

        # Calculate total dx based on victim's trade
        total_dx = victim_input / denominator

        if total_dx <= 0:
            # No viable dx can be calculated
            return None

        # Apply safety margin: use 85% of the maximum possible dx
        safe_dx = 0.85 * total_dx

        return safe_dx
    except Exception as e:
        print(f"Error in calculate_optimal_dx: {e}")
        return None


def handle_event(event):
    try:
        tx_hash = Web3.to_hex(event)
        trans = web3.eth.get_transaction(tx_hash)
        data = trans["input"]
        to = trans["to"]

        if to.lower() != pcsRouter.lower():
            return  # Transaction not related to PancakeSwap Router

        decoded = pcsContract.decode_function_input(data)
        function_name = decoded[0].fn_name
        params = decoded[1]

        if "swap" not in function_name:
            return  # Not a swap function

        # Determine amount_in and amount_out_min based on function parameters
        amount_in = None
        amount_out_min = None
        path = params.get("path", [])

        if function_name in ["swapExactETHForTokens", "swapExactETHForTokensSupportingFeeOnTransferTokens"]:
            amount_in = trans["value"]
            amount_out_min = params.get("amountOutMin")
        elif function_name == "swapETHForExactTokens":
            amount_in = trans["value"]
            amount_out_min = params.get("amountOut")  # amountOut is exact tokens desired
        elif function_name in ["swapExactTokensForETH", "swapExactTokensForETHSupportingFeeOnTransferTokens"]:
            amount_in = params.get("amountIn")
            amount_out_min = params.get("amountOutMin")
        elif function_name == "swapTokensForExactETH":
            amount_in = params.get("amountInMax")
            amount_out_min = params.get("amountOut")  # amountOut is exact ETH desired
        elif function_name in ["swapExactTokensForTokens", "swapExactTokensForTokensSupportingFeeOnTransferTokens"]:
            amount_in = params.get("amountIn")
            amount_out_min = params.get("amountOutMin")
        elif function_name == "swapTokensForExactTokens":
            amount_in = params.get("amountInMax")
            amount_out_min = params.get("amountOut")  # amountOut is exact tokens desired
        else:
            # Unknown function, skip
            print(f"Unknown swap function: {function_name}")
            return

        # Ensure amount_in and amount_out_min are present and valid
        if amount_in is None or amount_out_min is None or amount_in <= 0 or amount_out_min <= 0:
            return


        path = params.get("path", [])
        if len(path) < 2:
            return  # Invalid swap path

        # Check if it's a buy order
        if not is_buy_order(path):
            return  # Not a buy order

        # Base token and swapped token
        base_token = path[0]
        swapped_token = path[-1]

        # Fetch current reserves
        for dex in DEXES:
            try:
                pair_address = dex["factory_contract"].functions.getPair(swapped_token, base_token).call()
                if pair_address.lower() != "0x0000000000000000000000000000000000000000":
                    break
            except Exception:
                continue
        else:
            return  # No valid pair found in any DEX

        pair_contract = web3.eth.contract(address=Web3.to_checksum_address(pair_address), abi=PAIR_ABI)
        reserves = pair_contract.functions.getReserves().call()

        token0 = pair_contract.functions.token0().call()
        if token0.lower() == swapped_token.lower():
            reserve_token, reserve_base = reserves[0], reserves[1]
        else:
            reserve_token, reserve_base = reserves[1], reserves[0]

        # Get token decimals
        swapped_symbol, swapped_decimals = get_token_details(swapped_token)
        base_symbol, base_decimals = get_token_details(base_token)

        # Simulate reserves after the swap (constant product formula)
        reserve_token_scaled = reserve_token / (10 ** swapped_decimals)
        reserve_base_scaled = reserve_base / (10 ** base_decimals)

        # Calculate price before buy in base token
        if reserve_token_scaled > 0:
            price_before = reserve_base_scaled / reserve_token_scaled
        else:
            return

        # Input amount in base token
        input_base = amount_in / (10 ** base_decimals)

        # Adjust reserves assuming no slippage protection
        new_reserve_base = reserve_base + amount_in
        # Use constant product formula to adjust the token reserve
        new_reserve_token = reserve_token * reserve_base / new_reserve_base

        # Scale new reserves for post-buy price calculation
        new_reserve_token_scaled = new_reserve_token / (10 ** swapped_decimals)
        new_reserve_base_scaled = new_reserve_base / (10 ** base_decimals)

        # Calculate price after buy in base token
        if new_reserve_token_scaled > 0:
            price_after = new_reserve_base_scaled / new_reserve_token_scaled
        else:
            return

        # Calculate price impact
        impact = ((price_after - price_before) / price_before) * 100 if price_before > 0 else 0

        # Decode swap amounts
        swap_amounts = get_swap_amounts(amount_in, path)
        if swap_amounts is None:
            return

        # Generate Swap Path with Amounts
        swap_path_details = []
        for i, token_address in enumerate(path):
            symbol, decimals = get_token_details(token_address)
            adjusted_amount = swap_amounts[i] / (10 ** decimals)
            swap_path_details.append(f"{format_amount(adjusted_amount)} {symbol}({token_address})")

        swap_path = " -> ".join(swap_path_details)

        # Fetch and format DEX price details
        dex_price_details = {}
        for dex in DEXES:
            prices = {}
            for base_token_option, base_symbol_option, base_decimals_option in [
                (WBNB_TOKEN, "BNB", 18),
            ]:
                try:
                    pair_address = dex["factory_contract"].functions.getPair(swapped_token, base_token_option).call()
                    if pair_address.lower() != "0x0000000000000000000000000000000000000000":
                        pair_contract = web3.eth.contract(address=Web3.to_checksum_address(pair_address), abi=PAIR_ABI)
                        reserves = pair_contract.functions.getReserves().call()
                        token0 = pair_contract.functions.token0().call()
                        if token0.lower() == swapped_token.lower():
                            reserve_token_dex, reserve_base_dex = reserves[0], reserves[1]
                        else:
                            reserve_token_dex, reserve_base_dex = reserves[1], reserves[0]

                        scaled_reserve_token = reserve_token_dex / (10 ** swapped_decimals)
                        scaled_reserve_base = reserve_base_dex / (10 ** base_decimals_option)
                        prices[base_symbol_option] = scaled_reserve_base / scaled_reserve_token if scaled_reserve_token > 0 else None
                    else:
                        prices[base_symbol_option] = None
                except Exception:
                    prices[base_symbol_option] = None
            dex_price_details[dex["name"]] = prices

        # Format DEX price details in one line
        dex_price_lines = []
        # Extract slippage details

        for dex_name, prices in dex_price_details.items():
            formatted_prices = ", ".join(
                f"{format_amount(price)} {symbol}" if price is not None else f"N/A {symbol}"
                for symbol, price in prices.items()
            )
            dex_price_lines.append(f"{dex_name}: {formatted_prices}")

        # Calculate slippage
        amount_out_min = params.get("amountOutMin", 0)
        if amount_out_min > 0 and "path" in params:
            slippage = calculate_slippage(amount_in, amount_out_min, params["path"])
            if slippage is not None:
                slippage_formatted = f"{format_amount(slippage)}%"
            else:
                slippage_formatted = "N/A"
        else:
            slippage_formatted = "N/A"

        dex_fee = 0.9975  # For PancakeSwap's 0.25% fee
        dx = calculate_optimal_dx(
            victim_input=amount_in,
            min_tokens_out=amount_out_min,
            reserve_x=reserve_base,
            reserve_y=reserve_token,
            dex_fee=dex_fee
        )

        if dx is not None:
            dx_adjusted = dx / (10 ** base_decimals)  # Scale `dx` to human-readable units
            optimal_dx_message = f"{format_amount(dx_adjusted)} {base_symbol}"

            try:
                # Adjust reserves to simulate your frontrun
                new_reserve_base = reserve_base + dx
                new_reserve_token = reserve_token * reserve_base / new_reserve_base  # Constant product formula

                # Tokens received after investing `dx`
                tokens_received = reserve_token - new_reserve_token
                tokens_received_scaled = tokens_received / (10 ** swapped_decimals)

                # Value of tokens received in base token after the swap
                value_received_in_base = tokens_received_scaled * price_after

                # Calculate gas cost
                victim_gas_price = trans.get("gasPrice", 0)  # Gas price of the victim's transaction
                gas_limit = trans.get("gas", 0)  # Gas limit of the victim's transaction
                frontrun_gas_price = calculate_frontrun_gas_price(victim_gas_price, overpayment_percentage=0.50)  # Overpay by 75%
                gas_cost = gas_limit * frontrun_gas_price / (10 ** base_decimals)  # Gas cost in base token units

                # Profit calculation
                gross_profit = value_received_in_base - (dx / (10 ** base_decimals))
                net_profit = gross_profit - gas_cost  # Deduct gas cost from gross profit

                profit_formatted = f"{format_amount(net_profit)} {base_symbol}" if net_profit > 0 else "Unprofitable"
            except Exception as e:
                profit_formatted = "N/A"
        else:
            dx_adjusted = "N/A"
            optimal_dx_message = "N/A"
            profit_formatted = "N/A"

        print("----------------------------------------------------------------------------------------------------------------------")
        print(
            f"Transaction Hash: {tx_hash}\n"
            f"Swap Path: {swap_path}\n"
            f"Price of {swapped_symbol}: {', '.join(dex_price_lines)}\n"
            f"Price After Buy: {format_amount(price_after)} {base_symbol}, Impact: {format_amount(impact)}%\n"
            f"Gas: {trans.get('gas', 'N/A')}\n"
            f"Slippage: {slippage_formatted}, Optimal Investment: {optimal_dx_message}, Potential Profit: {profit_formatted}"
        )

    except Web3RPCError:
        return
    except Exception as e:
        return

async def log_loop(event_filter, poll_interval, executor):
    while True:
        try:
            events = event_filter.get_new_entries()
            for event in events:
                # Submit handle_event to the executor
                executor.submit(handle_event, event)
            await asyncio.sleep(poll_interval)
        except Web3RPCError:
            continue
        except Exception as e:
            print(f"Error in log loop: {e}")
            continue

def main():
    tx_filter = web3.eth.filter("pending")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    executor = ThreadPoolExecutor(max_workers=5)  # Adjust max_workers as needed
    try:
        loop.run_until_complete(asyncio.gather(log_loop(tx_filter, 1, executor)))
    finally:
        executor.shutdown(wait=True)
        loop.close()


# Entry point
if __name__ == "__main__":
    main()