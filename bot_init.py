import json
import os
import uvloop
import asyncio
import time
import sqlite3
from sqlite3 import Connection
from dotenv import load_dotenv
from paloma_sdk.client.lcd import AsyncLCDClient
from paloma_sdk.key.mnemonic import MnemonicKey
from paloma_sdk.core.coins import Coins
from paloma_sdk.client.lcd.api.tx import CreateTxOptions
from paloma_sdk.core.wasm import MsgInstantiateContract


async def dca_bot(network):
    dca_bot_address: str = network['ADDRESS']
    dca_bot_abi: str = network['ABI']
    paloma_lcd = os.environ['PALOMA_LCD']
    paloma_chain_id = os.environ['PALOMA_CHAIN_ID']
    paloma: AsyncLCDClient = AsyncLCDClient(
        url=paloma_lcd, chain_id=paloma_chain_id)
    paloma.gas_prices = "0.01ugrain"
    mnemonic: str = os.environ['PALOMA_KEY']
    acct: MnemonicKey = MnemonicKey(mnemonic=mnemonic)
    wallet = paloma.wallet(acct)
    payload = ""
    job_id = network['JOB_ID']
    result = await paloma.job_scheduler.create_job(
        wallet, job_id, dca_bot_address, dca_bot_abi, payload,
        network['CHAIN_TYPE'], network['CHAIN_REFERENCE_ID'])
    print(result)
    time.sleep(6)

    # Instantiate
    initialize_msg = {
        "job_id": job_id
    }
    code_id = os.environ['CODE_ID']
    funds = Coins()
    tx = await wallet.create_and_sign_tx(
        CreateTxOptions(
            msgs=[
                MsgInstantiateContract(
                    wallet.key.acc_address,
                    wallet.key.acc_address,
                    int(code_id),
                    job_id,
                    initialize_msg,
                    funds
                )
            ]
        )
    )
    result = await paloma.tx.broadcast_sync(tx)
    time.sleep(6)
    print(result)


def db_init():
    DB_PATH = os.environ['DB_PATH']
    CON: Connection = sqlite3.connect(DB_PATH)
    # Create Tables
    CON.execute("CREATE TABLE IF NOT EXISTS fetched_blocks (\
ID INTEGER PRIMARY KEY AUTOINCREMENT, \
block_number INTEGER, \
network_name TEXT, \
dex TEXT, \
bot TEXT);")

    CON.execute("CREATE TABLE IF NOT EXISTS deposits (\
id INTEGER PRIMARY KEY AUTOINCREMENT, \
deposit_id INTEGER NOT NULL, \
token0 TEXT NOT NULL, \
token1 TEXT NOT NULL, \
amount0 TEXT NOT NULL, \
depositor TEXT NOT NULL, \
contract TEXT, \
old BOOLEAN, \
number_trades INTEGER, \
remaining_counts INTEGER, \
interval INTEGER, \
starting_time INTEGER, \
deposit_price REAL, \
tracking_price REAL, \
profit_taking INTEGER, \
stop_loss INTEGER, \
expire INTEGER, \
withdraw_type INTEGER, \
withdraw_block INTEGER, \
withdraw_amount TEXT, \
withdrawer TEXT, \
network_name TEXT, \
dex_name TEXT, \
bot TEXT);")

    try:
        CON.execute("ALTER TABLE deposits ADD COLUMN deposit_id INTEGER;")
    except:
        print("Error while adding column deposit_id")
    try:
        CON.execute("ALTER TABLE deposits ADD COLUMN token0 TEXT;")
    except:
        print("Error while adding column token0")
    try:
        CON.execute("ALTER TABLE deposits ADD COLUMN token1 TEXT;")
    except:
        print("Error while adding column token1")
    try:
        CON.execute("ALTER TABLE deposits ADD COLUMN amount0 TEXT;")
    except:
        print("Error while adding column amount0")
    try:
        CON.execute("ALTER TABLE deposits ADD COLUMN depositor TEXT;")
    except:
        print("Error while adding column depositor")
    try:
        CON.execute("ALTER TABLE deposits ADD COLUMN number_trades INTEGER;")
    except:
        print("Error while adding column number_trades")
    try:
        CON.execute("ALTER TABLE deposits ADD COLUMN remaining_counts INTEGER;")
    except:
        print("Error while adding column remaining_counts")
    try:
        CON.execute("ALTER TABLE deposits ADD COLUMN interval INTEGER;")
    except:
        print("Error while adding column interval")
    try:
        CON.execute("ALTER TABLE deposits ADD COLUMN starting_time INTEGER;")
    except:
        print("Error while adding column starting_time")
    try:
        CON.execute("ALTER TABLE deposits ADD COLUMN network_name TEXT;")
    except:
        print("Error while adding column network_name")
    try:
        CON.execute("ALTER TABLE deposits ADD COLUMN dex_name TEXT;")
    except:
        print("Error while adding column dex_name")
    try:
        CON.execute("ALTER TABLE deposits ADD COLUMN bot TEXT;")
    except:
        print("Error while adding column bot")
    try:
        CON.execute("ALTER TABLE deposits ADD COLUMN is_stable_swap BOOLEAN;")
    except:
        print("Error while adding column is_stable_swap")

    CON.execute("CREATE INDEX IF NOT EXISTS deposit_idx ON deposits (deposit_id);")

    CON.commit()


async def main():
    load_dotenv()

    # Load JSON
    with open("networks.json") as f:
        networks = json.load(f)

    # Cycle through networks
    for network in networks:
        await dca_bot(network)
    
    db_init()


if __name__ == "__main__":
    uvloop.install()
    asyncio.run(main())
