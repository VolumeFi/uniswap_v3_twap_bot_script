import os
import uvloop
import asyncio
import json
import sqlite3
import time
from sqlite3 import Connection
from web3 import Web3
from web3.contract import Contract
from dotenv import load_dotenv
from paloma_sdk.client.lcd import AsyncLCDClient
from paloma_sdk.key.mnemonic import MnemonicKey
from paloma_sdk.client.lcd.api.tx import CreateTxOptions
from paloma_sdk.core.wasm import MsgExecuteContract
from paloma_sdk.core.coins import Coins

PALOMA_LCD = os.environ['PALOMA_LCD']
PALOMA_CHAIN_ID = os.environ['PALOMA_CHAIN_ID']
PALOMA: AsyncLCDClient = AsyncLCDClient(
    url=PALOMA_LCD, chain_id=PALOMA_CHAIN_ID)
PALOMA.gas_prices = "0.01ugrain"
MNEMONIC: str = os.environ['PALOMA_KEY']
ACCT: MnemonicKey = MnemonicKey(mnemonic=MNEMONIC)
WALLET = PALOMA.wallet(ACCT)
DB_PATH = os.environ['DB_PATH']

async def pancakeswap_bot(network):
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
        ID INTEGER PRIMARY KEY AUTOINCREMENT, \
        block_number INTEGER, \
        network_name TEXT);")

    CON.execute("CREATE TABLE IF NOT EXISTS deposits (\
        id INTEGER PRIMARY KEY AUTOINCREMENT, \
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

    res = CON.execute("SELECT * FROM fetched_blocks WHERE network_name = ? \
AND ID = (SELECT MAX(ID) FROM fetched_blocks WHERE network_name = ?);",
                      (NETWORK_NAME, NETWORK_NAME))
    from_block: int = 0
    result: tuple = res.fetchone()
    if result is None:
        data = (FROM_BLOCK - 1,)
        CON.execute(
            "INSERT INTO fetched_blocks (block_number) VALUES (?);", data)
        CON.commit()
        from_block = int(FROM_BLOCK)
    else:
        from_block = int(result[0]) + 1
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
        for log in deposit_logs:
            swap_id: int = int(log.args.swap_id)
            token0: str = log.args.token0
            token1: str = log.args.token1
            input_amount: str = log.args.input_amount
            number_trades: int = int(log.args.number_trades)
            interval: int = int(log.args.interval)
            starting_time: int = int(log.args.starting_time)
            remaining_counts: int = int(log.args.remaining_counts)
            data: tuple = (swap_id, token0, token1, input_amount,
                           number_trades, interval, starting_time,
                           remaining_counts, NETWORK_NAME, DEX)
            CON.execute("INSERT INTO deposits (swap_id, token0, token1, \
input_amount, number_trades, interval, starting_time, remaining_counts, \
network_name, dex_name) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);", data)
        CON.commit()
        swapped_logs = dca_sc.events.Swapped\
            .getLogs(fromBlock=i, toBlock=to_block)
        for log in swapped_logs:
            swap_id: int = int(log.args.swap_id)
            remaining_counts: int = int(log.args.remaining_counts)
            data: tuple = (remaining_counts, swap_id, remaining_counts,
                           NETWORK_NAME, DEX)
            CON.execute("UPDATE deposits SET remaining_counts = ? WHERE \
swap_id = ? AND remaining_counts > ? AND network_name = ? AND dex_name = ?;",
                        data)
        CON.commit()
        i += 10000
    data: tuple = (NETWORK_NAME, DEX)
    res = CON.execute("SELECT * FROM deposits WHERE remaining_counts > 0 AND \
network_name = ? AND dex_name = ?;", data)
    results = res.fetchall()
    current_time: int = int(time.time())
    for result in results:
        swap_id = int(result[0])
        number_trades = int(result[4])
        interval = int(result[5])
        starting_time = int(result[6])
        remaining_counts = int(result[7])
        if starting_time + interval * (number_trades - remaining_counts) \
           <= current_time:
            amount_out_min = dca_sc.functions.swap(swap_id, 0).call()
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
            result = await PALOMA.tx.broadcast_sync(tx)
            print(result)
        await time.sleep(6)


async def main():
    load_dotenv()

    # Load JSON
    with open("networks.json") as f:
        networks = json.load(f)

    # Cycle through networks
    for network in networks:
        await pancakeswap_bot(network)


if __name__ == "__main__":
    uvloop.install()
    asyncio.run(main())
