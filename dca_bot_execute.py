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
    dca_sc: Contract = w3.eth.contract(address=dca_bot_address, abi=dca_bot_abi)
    swap_id, amount_out_min, number_trades = dca_sc.functions.triggerable_deposit().call()
    try:
        log_file = open("./pancakeswap.log", "r")
    except:
        log_file = open("./pancakeswap.log", "w")
        log_file.close()
        log_file = open("./pancakeswap.log", "r")
    swapping_data = log_file.readlines()
    last_swapping_id = "-1" if len(swapping_data) < 2 else swapping_data[-2]
    num_trade = "-1" if len(swapping_data) < 2 else swapping_data[-1]
    print(swap_id, amount_out_min, number_trades)
    if int(number_trades) > 0 and (int(last_swapping_id) != int(swap_id) or int(num_trade) != int(number_trades)):
        payload = dca_sc.encodeABI("swap", [int(swap_id), int(amount_out_min)])[2:]
        paloma_lcd = os.environ['PALOMA_LCD']
        paloma_chain_id = os.environ['PALOMA_CHAIN_ID']
        paloma: AsyncLCDClient = AsyncLCDClient(url=paloma_lcd, chain_id=paloma_chain_id)
        paloma.gas_prices = "0.01ugrain"
        mnemonic: str = os.environ['PALOMA_KEY']
        acct: MnemonicKey = MnemonicKey(mnemonic=mnemonic)
        wallet = paloma.wallet(acct)

        job_id = os.environ['JOB_ID']
        result = await paloma.job_scheduler.execute_job(wallet, job_id, payload)
        print(result)
        log_file.close()
        log_file = open("./pancakeswap.log", "a")
        log_file.writelines([str(swap_id) + "\n", str(number_trades) + "\n"])
        log_file.close()


async def main():
    load_dotenv()
    await pancakeswap_bot()


if __name__ == "__main__":
    uvloop.install()
    asyncio.run(main())