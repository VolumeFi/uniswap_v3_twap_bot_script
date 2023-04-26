import os
import uvloop
import asyncio
from web3 import Web3
from web3.contract import Contract
from dotenv import load_dotenv
from paloma_sdk.client.lcd import AsyncLCDClient
from paloma_sdk.key.mnemonic import MnemonicKey


async def pancakeswap_bot():
    node: str = os.environ['BNB_NODE']
    w3: Web3 = Web3(Web3.HTTPProvider(node))
    dca_bot_address: str = os.environ['PANCAKESWAP_DCA_BOT']
    dca_bot_abi: str = os.environ['DCA_BOT_ABI']
    paloma_lcd = os.environ['PALOMA_LCD']
    paloma_chain_id = os.environ['PALOMA_CHAIN_ID']
    paloma: AsyncLCDClient = AsyncLCDClient(url=paloma_lcd, chain_id=paloma_chain_id)
    paloma.gas_prices = "0.01ugrain"
    mnemonic: str = os.environ['PALOMA_KEY']
    acct: MnemonicKey = MnemonicKey(mnemonic=mnemonic)
    wallet = paloma.wallet(acct)
    dca_sc: Contract = w3.eth.contract(address=dca_bot_address, abi=dca_bot_abi)
    payload = dca_sc.encodeABI("swap", [0, 0])[2:]
    job_id = os.environ['JOB_ID']
    result = await paloma.job_scheduler.create_job(wallet, job_id, dca_bot_address, dca_bot_abi, payload, "evm", "bnb-main")
    print(result)


async def main():
    load_dotenv()
    await pancakeswap_bot()


if __name__ == "__main__":
    uvloop.install()
    asyncio.run(main())