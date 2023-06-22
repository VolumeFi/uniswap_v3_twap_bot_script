# PancakeSwap Bot

This repository contains scripts to interact with decentralized exchanges such as PancakeSwap, Uniswap, and Apeswap. The scripts utilize `web3` and `paloma_sdk` to connect with the blockchain and perform specific tasks.

## Setup

1. **Clone the repository** `git clone https://github.com/your-github-username/pancakeswap-bot.git`
2. **Navigate to the cloned directory** `cd pancakeswap-bot`
3. **Install dependencies** `pip install -r requirements.txt`


## Environment Variables

The scripts rely on certain environment variables. To set them up, create a `.env` file in the project root with the following entries:

```
PALOMA_LCD=<lcd-endpoint>
PALOMA_CHAIN_ID=<chain-id>
PALOMA_KEY=<mnemonic-key>
```


Replace `<lcd-endpoint>`, `<chain-id>`, and `<mnemonic-key>` with actual values.

## Network Configuration

The scripts use a `networks.json` file for network-specific configurations. This file should contain an array of objects, each representing a network. The networks are cycled through when the scripts are run.

Here's the structure of a network configuration:

```json
[{
  "NODE": "<node-url>",
  "ABI": "<contract-abi>",
  "ADDRESS": "<contract-address>",
  "JOB_ID": "<job-id>",
  "CHAIN_TYPE": "<chain-type>",
  "CHAIN_REFERENCE_ID": "<chain-reference-id>",
  "COINGECKO_CHAIN_ID": "<coingecko-chain-id>",
  "NETWORK_NAME": "<network-name>",
  "WETH": "<weth-address>",
  "FROM_BLOCK": <from-block>,
  "CW": "<cw>",
  "DEX": "<dex-name>"
}]
```
Replace the placeholders with actual values.

## Running the Scripts

The following scripts are available:

bot_execute.py: Runs the PancakeSwap bot.
bot_init.py: Calls the triggerable deposit function and performs swaps if applicable.
bot_set_paloma.py: Executes a set_paloma command.

To run a script, use the following command:
`python <script-name>.py`


