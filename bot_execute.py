import os
import uvloop
import asyncio
import json
import sqlite3
import time
import requests
import re

from aiohttp import web
from sqlite3 import Connection
from web3 import Web3
from web3.contract import Contract
from dotenv import load_dotenv
from paloma_sdk.client.lcd import AsyncLCDClient, AsyncWallet
from paloma_sdk.key.mnemonic import MnemonicKey
from paloma_sdk.client.lcd.api.tx import CreateTxOptions
from paloma_sdk.core.wasm import MsgExecuteContract
from paloma_sdk.core.coins import Coins
from mixpanel import Mixpanel
import sentry_sdk

sentry_sdk.init(
    dsn="https://955ac0a74d244e2c914767a351d4d069@o1200162.ingest.sentry.io/4505082653573120",
    # Set traces_sample_rate to 1.0 to capture 100%
    # of transactions for performance monitoring.
    # We recommend adjusting this value in production.
    traces_sample_rate=1.0,
)

load_dotenv()
mp = Mixpanel('eaae482845dadd88e1ce07b9fa03dd6b')

PALOMA_LCD = os.environ['PALOMA_LCD']
PALOMA_CHAIN_ID = os.environ['PALOMA_CHAIN_ID']
TELEGRAM_ALERT_API = os.environ['TELEGRAM_ALERT_API']
MNEMONIC: str = os.environ['PALOMA_KEY']
DB_PATH = os.environ['DB_PATH']
SLIPPAGE = int(os.environ['SLIPPAGE'])
SLIPPAGE_STABLE = int(os.environ['SLIPPAGE_STABLE'])
COINGECKO_API_KEY = os.environ['COINGECKO_API_KEY']
DENOMINATOR = 10000
BOT: str = 'twap'
MAX_SIZE = 8
VETH = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"
BOT_NAME = 'TWAP'
# Telegram alert return type
SUCCESS = 1  # All success withdrawn type.
EXPIRED = 2  # For Limit order, Stop loss bot type.
REMAINING = 3  # For DCA bot type.

price = {}

paloma_lcd_client: AsyncLCDClient = None
paloma_wallet: AsyncWallet = None


async def dca_bot(network):
    global price, paloma_lcd_client, paloma_wallet

    async def inner():
        await asyncio.sleep(6)

    node: str = network['NODE']
    w3: Web3 = Web3(Web3.HTTPProvider(node))
    dca_bot_address: str = network['ADDRESS']
    dca_bot_abi: str = network['ABI']
    FROM_BLOCK: int = int(network['FROM_BLOCK'])
    DEX: str = network['DEX']
    NETWORK_NAME: str = network['NETWORK_NAME']
    COINGECKO_CHAIN_ID: str = network['COINGECKO_CHAIN_ID']
    COINGECKO_COIN_ID: str = network['COINGECKO_COIN_ID']
    CON: Connection = sqlite3.connect(DB_PATH)
    if paloma_lcd_client is None or paloma_wallet is None:
        paloma_lcd_client = AsyncLCDClient(url=PALOMA_LCD, chain_id=PALOMA_CHAIN_ID)
        paloma_lcd_client.gas_prices = "0.01ugrain"
        ACCT: MnemonicKey = MnemonicKey(mnemonic=MNEMONIC)
        paloma_wallet = paloma_lcd_client.wallet(ACCT)
    BOT_NAME = re.sub(r'v\d+$', '', DEX)

    # Create Tables

    DEX: str = network['DEX']

    res = CON.execute(
        "SELECT * FROM fetched_blocks WHERE ID = (SELECT MAX(ID) FROM fetched_blocks WHERE network_name = ? AND dex = ? AND bot = ? AND contract_instance = ?);",
        (NETWORK_NAME, DEX, BOT, dca_bot_address)
    )
    from_block: int = 0
    result: tuple = res.fetchone()
    if result is None:
        data = (FROM_BLOCK - 1, NETWORK_NAME, DEX, BOT, dca_bot_address)
        CON.execute(
            "INSERT INTO fetched_blocks (block_number, network_name, dex, bot, contract_instance) VALUES (?, ?, ?, ?, ?);", data
        )
        CON.commit()
        from_block = int(FROM_BLOCK)
    else:
        incremented_block = int(result[1]) + 1
        from_block = int(FROM_BLOCK) if incremented_block < int(FROM_BLOCK) else incremented_block

    BLOCK_NUMBER: int = int(w3.eth.get_block_number())
    dca_sc: Contract = w3.eth.contract(address=dca_bot_address, abi=dca_bot_abi)
    i: int = from_block
    batch_sql = []
    while i <= BLOCK_NUMBER:
        to_block: int = i + 9999
        if to_block > BLOCK_NUMBER:
            to_block = BLOCK_NUMBER
        deposit_logs = dca_sc.events.Deposited.getLogs(fromBlock=i, toBlock=to_block)
        for log in deposit_logs:
            deposit_id: int = int(log.args.deposit_id)
            token0: str = log.args.token0
            token1: str = log.args.token1
            input_amount: str = str(log.args.input_amount)
            number_trades: int = int(log.args.number_trades)
            interval: int = int(log.args.interval)
            starting_time: int = int(log.args.starting_time)
            remaining_counts: int = int(log.args.number_trades)
            depositor: str = log.args.depositor
            is_stable_swap: bool = bool(log.args.is_stable_swap)
            if token0 not in price.keys():
                if token0 == VETH:
                    url: str = "https://pro-api.coingecko.com/api/v3/simple/price"
                    headers = {"Content-Type": "application/json"}
                    params = {
                        'ids': COINGECKO_COIN_ID,
                        'vs_currencies': 'usd',
                        'x_cg_pro_api_key': COINGECKO_API_KEY
                    }
                    response: requests.Response = requests.get(url, params=params, headers=headers)
                    result = response.json()
                    price[token0] = result[list(result)[0]]['usd']
                else:
                    url: str = "https://pro-api.coingecko.com/api/v3/simple/token_price/" + COINGECKO_CHAIN_ID
                    headers = {"Content-Type": "application/json"}
                    params = {
                        'contract_addresses': token0,
                        'vs_currencies': 'usd',
                        'x_cg_pro_api_key': COINGECKO_API_KEY
                    }
                    response: requests.Response = requests.get(url, params=params, headers=headers)
                    result = response.json()
                    price[token0] = result[list(result)[0]]['usd']
            data: tuple = (deposit_id, token0, token1, input_amount, depositor, number_trades, remaining_counts, interval, starting_time, price[token0], NETWORK_NAME, DEX, BOT, dca_bot_address)
            cursor = CON.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM deposits WHERE deposit_id = ? AND network_name = ? AND dex_name = ? AND bot = ? AND contract = ?;",
                (deposit_id, NETWORK_NAME, DEX, BOT, dca_bot_address))
            result = cursor.fetchone()

            if result[0] == 0:
                sql = "INSERT INTO deposits (deposit_id, token0, token1, amount0, depositor, number_trades, remaining_counts, interval, starting_time, deposit_price, network_name, dex_name, bot, contract, is_stable_swap) VALUES ({0}, '{1}', '{2}', '{3}', '{4}', {5}, {6}, {7}, {8}, {9}, '{10}', '{11}', '{12}', '{13}', {14});".format(deposit_id, token0, token1, input_amount, depositor, number_trades, remaining_counts, interval, starting_time, price[token0], NETWORK_NAME, DEX, BOT, dca_bot_address, is_stable_swap)
                batch_sql.append(sql)

                mp.track(str(deposit_id), 'bot-add', {
                    'bot': BOT,
                    'dex': DEX,
                    'network': NETWORK_NAME
                })
            else:
                print("Skipping duplicate entry:", data)

        swapped_logs = dca_sc.events.Swapped.getLogs(fromBlock=i, toBlock=to_block)
        for log in swapped_logs:
            deposit_id: int = int(log.args.deposit_id)
            remaining_counts: int = int(log.args.remaining_counts)
            block_number: int = int(log.blockNumber)
            cursor = CON.execute("SELECT token0 FROM deposits WHERE deposit_id = ? AND network_name = ? AND dex_name = ? AND bot = ? AND contract = ?;", (deposit_id, NETWORK_NAME, DEX, BOT, dca_bot_address))
            result = cursor.fetchone()
            token0 = str(result[0])
            if token0 not in price.keys():
                if token0 == VETH:
                    url: str = "https://pro-api.coingecko.com/api/v3/simple/price"
                    headers = {"Content-Type": "application/json"}
                    params = {
                        'ids': COINGECKO_COIN_ID,
                        'vs_currencies': 'usd',
                        'x_cg_pro_api_key': COINGECKO_API_KEY
                    }
                    response: requests.Response = requests.get(url, params=params, headers=headers)
                    result = response.json()
                    price[token0] = result[list(result)[0]]['usd']
                else:
                    url: str = "https://pro-api.coingecko.com/api/v3/simple/token_price/" + COINGECKO_CHAIN_ID
                    headers = {"Content-Type": "application/json"}
                    params = {
                        'contract_addresses': token0,
                        'vs_currencies': 'usd',
                        'x_cg_pro_api_key': COINGECKO_API_KEY
                    }
                    response: requests.Response = requests.get(url, params=params, headers=headers)
                    result = response.json()
                    price[token0] = result[list(result)[0]]['usd']
            sql = "UPDATE deposits SET remaining_counts = {0}, tracking_price = {1} WHERE deposit_id = {2} AND remaining_counts > {3} AND network_name = '{4}' AND dex_name = '{5}' AND bot = '{6}' AND contract = '{7}';".format(remaining_counts, price[token0], deposit_id, remaining_counts, NETWORK_NAME, DEX, BOT, dca_bot_address)
            batch_sql.append(sql)
            if remaining_counts == 0:
                sql = "UPDATE deposits SET withdraw_block = {0} WHERE deposit_id = {1} AND network_name = '{2}' AND dex_name = '{3}' AND bot = '{4}' AND contract = '{5}';".format(block_number, deposit_id, NETWORK_NAME, DEX, BOT, dca_bot_address)
                batch_sql.append(sql)
            try:
                botInfo = await getBot(deposit_id, dca_bot_address)
                tokenName = await getBotName(botInfo[1])
                if botInfo:
                    params = {
                        'depositor': botInfo[0],
                        'kind': REMAINING if remaining_counts > 0 else SUCCESS,
                        'tokenName': tokenName,
                        'botType': BOT_NAME,
                        'remainCounts': remaining_counts
                    }
                    requests.get(TELEGRAM_ALERT_API, params=params)
            except Exception as e:
                print("Telegram alert error occurred:", str(e))

        canceled_logs = dca_sc.events.Canceled.getLogs(fromBlock=i, toBlock=to_block)
        for log in canceled_logs:
            deposit_id: int = int(log.args.deposit_id)
            block_number: int = int(log.blockNumber)
            cursor = CON.execute("SELECT token0 FROM deposits WHERE deposit_id = ? AND network_name = ? AND dex_name = ? AND bot = ? AND contract = ?;", (deposit_id, NETWORK_NAME, DEX, BOT, dca_bot_address))
            result = cursor.fetchone()
            token0 = str(result[0])
            if token0 not in price.keys():
                if token0 == VETH:
                    url: str = "https://pro-api.coingecko.com/api/v3/simple/price"
                    headers = {"Content-Type": "application/json"}
                    params = {
                        'ids': COINGECKO_COIN_ID,
                        'vs_currencies': 'usd',
                        'x_cg_pro_api_key': COINGECKO_API_KEY
                    }
                    response: requests.Response = requests.get(url, params=params, headers=headers)
                    result = response.json()
                    price[token0] = result[list(result)[0]]['usd']
                else:
                    url: str = "https://pro-api.coingecko.com/api/v3/simple/token_price/" + COINGECKO_CHAIN_ID
                    headers = {"Content-Type": "application/json"}
                    params = {
                        'contract_addresses': token0,
                        'vs_currencies': 'usd',
                        'x_cg_pro_api_key': COINGECKO_API_KEY
                    }
                    response: requests.Response = requests.get(url, params=params, headers=headers)
                    result = response.json()
                    price[token0] = result[list(result)[0]]['usd']
            sql = "UPDATE deposits SET withdraw_block = {0}, remaining_counts = {1}, tracking_price = {2} WHERE deposit_id = {3} AND network_name = '{4}' AND dex_name = '{5}' AND bot = '{6}' AND contract = '{7}';".format(block_number, 0, price[token0], deposit_id, NETWORK_NAME, DEX, BOT, dca_bot_address)
            batch_sql.append(sql)
        i += 10000
    sql = "UPDATE fetched_blocks SET block_number = {0} WHERE network_name = '{1}' AND dex = '{2}' AND bot = '{3}' AND contract_instance = '{4}';".format(BLOCK_NUMBER, NETWORK_NAME, DEX, BOT, dca_bot_address)
    batch_sql.append(sql)

    for query in batch_sql:
        CON.execute(query)
        CON.commit()

    CON.execute("PRAGMA busy_timeout = 5000")
    CON.execute("PRAGMA journal_mode = WAL")

    data: tuple = (NETWORK_NAME, DEX, BOT, dca_bot_address)
    res = CON.execute("SELECT deposit_id, number_trades, interval, starting_time, remaining_counts, depositor, is_stable_swap FROM deposits WHERE remaining_counts > 0 AND network_name = ? AND dex_name = ? AND bot = ? AND contract = ?;", data)
    results = res.fetchall()
    current_time: int = int(time.time())
    deposit_ids = []
    remaining_countlist = []
    stable_swaplist = []
    dca_cw = network['CW']
    for result in results:
        deposit_id = int(result[0])
        number_trades = int(result[1])
        interval = int(result[2])
        starting_time = int(result[3])
        remaining_counts = int(result[4])
        depositor = result[5]
        is_stable_swap = bool(result[6])
        try:
            if starting_time + interval * (number_trades - remaining_counts) <= current_time:
                deposit_ids.append(deposit_id)
                remaining_countlist.append(remaining_counts)
                stable_swaplist.append(is_stable_swap)
                if len(deposit_ids) >= MAX_SIZE:
                    amount_out_min = dca_sc.functions.multiple_swap_view(deposit_ids, remaining_countlist).call({"from": "0x0000000000000000000000000000000000000000"})
                    deposits = []
                    i = 0
                    for deposit_id in deposit_ids:
                        slippage = SLIPPAGE
                        if stable_swaplist[i]:
                            slippage = SLIPPAGE_STABLE
                        deposits.append({"deposit_id": int(deposit_id), "remaining_count": int(remaining_countlist[i]), "amount_out_min": str(int(int(amount_out_min[i]) * (DENOMINATOR - slippage) / DENOMINATOR))})
                        i += 1
                    tx = await paloma_wallet.create_and_sign_tx(CreateTxOptions(msgs=[
                        MsgExecuteContract(paloma_wallet.key.acc_address, dca_cw, {
                            "put_swap": {
                                "deposits": deposits
                            }
                        }, Coins())
                    ]))
                    result = await paloma_lcd_client.tx.broadcast_sync(tx)
                    time.sleep(6)
                    deposit_ids = []
                    remaining_countlist = []
                    stable_swaplist = []
        except Exception as e:
            print("An error occurred:", str(e))

    if len(deposit_ids) > 0:
        amount_out_min = dca_sc.functions.multiple_swap_view(deposit_ids, remaining_countlist).call({"from": "0x0000000000000000000000000000000000000000"})
        deposits = []
        i = 0
        for deposit_id in deposit_ids:
            slippage = SLIPPAGE
            if stable_swaplist[i]:
                slippage = SLIPPAGE_STABLE
            deposits.append({"deposit_id": int(deposit_id), "remaining_count": int(remaining_countlist[i]), "amount_out_min": str(int(int(amount_out_min[i]) * (DENOMINATOR - slippage) / DENOMINATOR))})
            i += 1
        tx = await paloma_wallet.create_and_sign_tx(CreateTxOptions(msgs=[
            MsgExecuteContract(paloma_wallet.key.acc_address, dca_cw, {
                "put_swap": {
                    "deposits": deposits
                }
            }, Coins())
        ]))
        result = await paloma_lcd_client.tx.broadcast_sync(tx)
        time.sleep(6)
    return await inner()


async def getBot(deposit_id, dca_bot_address):
    CON: Connection = sqlite3.connect(DB_PATH)
    res = CON.execute(
        "SELECT depositor, token0 FROM deposits WHERE deposit_id = ? AND contract = ?;",
        (deposit_id, dca_bot_address))
    result = res.fetchone()
    if result is not None:
        return result
    else:
        return None


async def getBotName(tokenAddress):
    try:
        coinInfo = None
        # Load JSON
        # Opening JSON file
        f = open('gecko.json')
        geckoTokens = json.load(f)

        # Cycle through networks
        for geckoToken in geckoTokens:
            if tokenAddress.lower() != VETH.lower():
                for value in geckoToken['platforms'].values():
                    if value and value.lower() == tokenAddress.lower():
                        coinInfo = geckoToken
                        break
            else:
                if geckoToken['id'] == "ethereum":
                    coinInfo = geckoToken
            if coinInfo:
                break
        if coinInfo is not None:
            return coinInfo['name']
        else:
            return None
    except Exception as e:
        print("Get bot info error occurred:", str(e))


async def handle(request):
    return web.Response(text="true")

async def web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, 'localhost', 8080)
    await site.start()

async def main():
    global price
    # Load JSON
    with open("networks.json") as f:
        networks = json.load(f)

    async def worker():
        while True:
            price = {}
            try:
                for network in networks:
                    await dca_bot(network)
            except KeyboardInterrupt:
                break
            await asyncio.sleep(1)

    await asyncio.gather(worker(), web_server())

if __name__ == "__main__":
    uvloop.install()
    asyncio.run(main())
