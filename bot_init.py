import json
import os
import uvloop
import asyncio
import time
from web3 import Web3
from web3.contract import Contract
from dotenv import load_dotenv
from paloma_sdk.client.lcd import AsyncLCDClient
from paloma_sdk.key.mnemonic import MnemonicKey
from paloma_sdk.core.coins import Coins
from paloma_sdk.client.lcd.api.tx import CreateTxOptions
from paloma_sdk.core.wasm import MsgInstantiateContract


async def pancakeswap_bot(network):
    node: str = network['NODE']
    w3: Web3 = Web3(Web3.HTTPProvider(node))
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
    dca_sc: Contract = w3.eth.contract(
        address=dca_bot_address, abi=dca_bot_abi)
    payload = dca_sc.encodeABI("swap", [0, 0])[2:]
    job_id = network['JOB_ID']
    result = await paloma.job_scheduler.create_job(
        wallet, job_id, dca_bot_address, dca_bot_abi, payload, network['CHAIN_TYPE'],
        network['CHAIN_REFERENCE_ID'])
    print(result)
    time.sleep(6)

    # Instantiate
    initialize_msg = {
        "retry_delay": 30,
        "job_id": job_id
    }
    code_id = network['ADDRESS']
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
