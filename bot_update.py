import json
import os
import uvloop
import asyncio
import time
from dotenv import load_dotenv
from paloma_sdk.client.lcd import AsyncLCDClient
from paloma_sdk.key.mnemonic import MnemonicKey
from paloma_sdk.core.coins import Coins
from paloma_sdk.client.lcd.api.tx import CreateTxOptions
from paloma_sdk.core.wasm import MsgExecuteContract


async def twap_bot(network):
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
    creator = wallet.key.acc_address
    signers = [wallet.key.acc_address]
    result = await paloma.job_scheduler.create_job(
        wallet, job_id, dca_bot_address, dca_bot_abi, payload,
        network['CHAIN_TYPE'], network['CHAIN_REFERENCE_ID'], creator, signers)
    print(result)
    time.sleep(10)

    # Instantiate

    dca_cw = network['CW']
    tx = await wallet.create_and_sign_tx(CreateTxOptions(msgs=[
        MsgExecuteContract(wallet.key.acc_address, dca_cw, {
                "update_job_id": {
                    "new_job_id": job_id
                }
            }, Coins())
    ]))
    result = await paloma.tx.broadcast_sync(tx)
    time.sleep(10)
    print(result)


async def main():
    load_dotenv()

    # Load JSON
    with open("networks.json") as f:
        networks = json.load(f)

    # Cycle through networks
    for network in networks:
        await twap_bot(network)

if __name__ == "__main__":
    uvloop.install()
    asyncio.run(main())
