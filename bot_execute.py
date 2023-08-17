import os
import uvloop
import asyncio
import json
import sqlite3
import time
import requests
from sqlite3 import Connection
from web3 import Web3
from web3.contract import Contract
from dotenv import load_dotenv
from paloma_sdk.client.lcd import AsyncLCDClient
from paloma_sdk.key.mnemonic import MnemonicKey
from paloma_sdk.client.lcd.api.tx import CreateTxOptions
from paloma_sdk.core.wasm import MsgExecuteContract
from paloma_sdk.core.coins import Coins
from mixpanel import Mixpanel

mp = Mixpanel('eaae482845dadd88e1ce07b9fa03dd6b')

PALOMA_LCD = os.environ['PALOMA_LCD']
PALOMA_CHAIN_ID = os.environ['PALOMA_CHAIN_ID']
PALOMA: AsyncLCDClient = AsyncLCDClient(
    url=PALOMA_LCD, chain_id=PALOMA_CHAIN_ID)
TELEGRAM_ALERT_API = os.environ['TELEGRAM_ALERT_API']
PALOMA.gas_prices = "0.01ugrain"
MNEMONIC: str = os.environ['PALOMA_KEY']
ACCT: MnemonicKey = MnemonicKey(mnemonic=MNEMONIC)
WALLET = PALOMA.wallet(ACCT)
DB_PATH = os.environ['DB_PATH']
VETH = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"
BOT_NAME = 'TWAP'
# Telegram alert return type
SUCCESS = 1 # All success withdrawn type.
EXPIRED = 2 # For Limit order, Stop loss bot type.
REMAINING = 3 # For DCA bot type.

async def pancakeswap_bot(network):
    async def inner():
        await time.sleep(6)

    node: str = network['NODE']
    w3: Web3 = Web3(Web3.HTTPProvider(node))
    dca_bot_address: str = network['ADDRESS']
    dca_bot_abi: str = network['ABI_VIEW']
    FROM_BLOCK: int = int(network['FROM_BLOCK'])
    DEX: str = network['DEX']
    NETWORK_NAME: str = network['NETWORK_NAME']
    CON: Connection = sqlite3.connect(DB_PATH)
    # Create Tables
    CON.execute("CREATE TABLE IF NOT EXISTS fetched_blocks (\
        ID INTEGER PRIMARY KEY, \
        block_number INTEGER, \
        network_name TEXT, \
        dex TEXT, \
        bot TEXT);")

    CON.execute("CREATE TABLE IF NOT EXISTS deposits (\
        id INTEGER PRIMARY KEY, \
        deposit_id INTEGER NOT NULL, \
        token0 TEXT NOT NULL, \
        token1 TEXT NOT NULL, \
        amount0 TEXT NOT NULL, \
        amount1 TEXT NOT NULL, \
        depositor TEXT NOT NULL, \
        deposit_price REAL, \
        tracking_price REAL, \
        profit_taking INTEGER, \
        stop_loss INTEGER, \
        withdraw_type INTEGER, \
        withdraw_block INTEGER, \
        withdraw_amount TEXT, \
        withdrawer TEXT, \
        network_name TEXT, \
        dex_name TEXT, \
        bot TEXT);")

    CON.execute("CREATE INDEX IF NOT EXISTS deposit_idx ON deposits (deposit_id);")

    CON.execute("CREATE TABLE IF NOT EXISTS users (\
        chat_id TEXT PRIMARY KEY, \
        address TEXT NOT NULL);")

    # Check if columns exist in the 'deposits' table
    cursor = CON.execute("PRAGMA table_info(deposits);")
    columns = [column[1] for column in cursor.fetchall()]

    if 'number_trades' not in columns:
        CON.execute("ALTER TABLE deposits ADD COLUMN number_trades INTEGER;")

    if 'remaining_counts' not in columns:
        CON.execute("ALTER TABLE deposits ADD COLUMN remaining_counts INTEGER;")

    if 'interval' not in columns:
        CON.execute("ALTER TABLE deposits ADD COLUMN interval INTEGER;")

    if 'starting_time' not in columns:
        CON.execute("ALTER TABLE deposits ADD COLUMN starting_time INTEGER;")

    CON.commit()

    DEX: str = network['DEX']
    BOT: str = 'dca'

    res = CON.execute(
        "SELECT * FROM fetched_blocks WHERE network_name = ? AND dex = ? AND bot = ? AND contract_instance = ?\
        AND ID = (SELECT MAX(ID) FROM fetched_blocks WHERE network_name = ? AND dex = ? AND bot = ? AND contract_instance = ?);",
        (NETWORK_NAME, DEX, BOT, dca_bot_address, NETWORK_NAME, DEX, BOT, dca_bot_address)
    )


    from_block: int = 0
    result: tuple = res.fetchone()
    if result is None:
        DEX: str = network['DEX']
        BOT: str = 'dca'

        data = (FROM_BLOCK - 1, NETWORK_NAME, DEX, BOT, dca_bot_address)
        CON.execute(
            "INSERT INTO fetched_blocks (block_number, network_name, dex, bot, contract_instance) VALUES (?, ?, ?, ?, ?);", data
        )
        CON.commit()
        from_block = int(FROM_BLOCK)
    else:
        incremented_block = int(result[0]) + 1
        from_block = int(FROM_BLOCK) if incremented_block < int(FROM_BLOCK) else incremented_block

    BLOCK_NUMBER: int = int(w3.eth.get_block_number())
    dca_sc: Contract = w3.eth.contract(
        address=dca_bot_address, abi=dca_bot_abi)
    i: int = from_block
    while i <= BLOCK_NUMBER:
        to_block: int = i + 9999
        if to_block > BLOCK_NUMBER:
            to_block = BLOCK_NUMBER
        deposit_logs = dca_sc.events.Deposited\
            .getLogs(fromBlock=i, toBlock=to_block)

        # Acquire an exclusive lock on the database
        CON.execute("BEGIN EXCLUSIVE;")

        try:
            for log in deposit_logs:
                swap_id: int = int(log.args.swap_id)
                token0: str = log.args.token0
                token1: str = log.args.token1
                input_amount: str = log.args.input_amount
                number_trades: int = int(log.args.number_trades)
                interval: int = int(log.args.interval)
                starting_time: int = int(log.args.starting_time)
                remaining_counts: int = int(log.args.number_trades)
                depositor: str = log.args.depositor
                data: tuple = (swap_id, token0, token1, input_amount, 0, depositor,
                               number_trades, interval, starting_time,
                               remaining_counts, NETWORK_NAME, DEX, 'dca', dca_bot_address)

                cursor = CON.cursor()
                cursor.execute(
                    "SELECT COUNT(*) FROM deposits WHERE deposit_id = ? AND network_name = ? AND dex_name = ? AND bot = ? AND contract = ?;",
                    (swap_id, NETWORK_NAME, DEX, 'dca', dca_bot_address)
                )
                result = cursor.fetchone()

                if result[0] == 0:
                    CON.execute(
                        "INSERT INTO deposits (deposit_id, token0, token1, amount0, amount1, depositor, number_trades, interval, starting_time, remaining_counts, network_name, dex_name, bot, contract) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
                        data)

                    mp.track(str(swap_id), 'bot-add', {
                        'bot': 'dca',
                        'dex': DEX,
                        'network': NETWORK_NAME
                    })
                else:
                    print("Skipping duplicate entry:", data)

            CON.commit()

        except:
            CON.rollback()
            raise

        finally:
            CON.commit()

        swapped_logs = dca_sc.events.Swapped\
            .getLogs(fromBlock=i, toBlock=to_block)
        for log in swapped_logs:
            swap_id: int = int(log.args.swap_id)
            remaining_counts: int = int(log.args.remaining_counts)
            data: tuple = (remaining_counts, swap_id, remaining_counts, NETWORK_NAME, DEX, 'dca', dca_bot_address)
            CON.execute(
                "UPDATE deposits SET remaining_counts = ? WHERE swap_id = ? AND remaining_counts > ? AND network_name = ? AND dex_name = ? AND bot = ? AND contract = ?;",
                data)

            try:
                botInfo = await getBot(swap_id, dca_bot_address)
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

        CON.commit()
        i += 10000
    data: tuple = (NETWORK_NAME, DEX, 'dca', dca_bot_address)
    res = CON.execute(
        "SELECT deposit_id, number_trades, interval, starting_time, remaining_counts, depositor FROM deposits WHERE remaining_counts > 0 AND network_name = ? AND dex_name = ? AND bot = ? AND contract = ?;",
        data)
    results = res.fetchall()
    current_time: int = int(time.time())
    for result in results:
        swap_id = int(result[0])
        number_trades = int(result[1])
        interval = int(result[2])
        starting_time = int(result[3])
        remaining_counts = int(result[4])
        depositor = result[5]
        try:
            if starting_time + interval * (number_trades - remaining_counts) <= current_time:
                amount_out_min = dca_sc.functions.swap(swap_id, 0).call({"from": depositor})
                dca_cw = network['CW']
                tx = await WALLET.create_and_sign_tx(CreateTxOptions(msgs=[
                    MsgExecuteContract(WALLET.key.acc_address, dca_cw, {
                        "swap": {
                            "swap_id": str(swap_id),
                            "amount_out_min": str(amount_out_min),
                            "number_trades": str(number_trades)
                        }
                    }, Coins())
                ]))
                PALOMA.tx.broadcast_sync(tx)
        except Exception as e:
            print("An error occurred:", str(e))

            #print(result)
    return inner()

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


async def main():
    load_dotenv()

    # Load JSON
    with open("networks.json") as f:
        networks = json.load(f)

    # Cycle through networks
    while True:
        for network in networks:
            await pancakeswap_bot(network)


if __name__ == "__main__":
    uvloop.install()
    asyncio.run(main())
