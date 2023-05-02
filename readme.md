
This is a hobby repository, where I keep track of my journey into cryptocurrencies and EVM-based smart contracts. This repo contains various projects and tools I've created along the way.
<br><br><br>

### ├── altcoin 💩

Containing code for interacting with and monitoring EVM-compatible blockchains and smart contracts for various tasks. These implementations are mainly written in python with web3 but also include Solidity and Golang codes.
#### **web3bsc**
* wallet factory i.e. BIP32 address generation using a single seed phrase
* future contract address from deployer and nonce
* scanning all new block transactions listening to events or specific function calls real-time
* wallet balance calculation
* auto-swap all tokens to BNB in a wallet
* cumulative transfer between multiple accounts
* direct ERC20, DEX function calls without ABI
* sqlite3 database for storing tokens and related information for multiple chains and DEXs
* swap tokens with multiple account
* copy trading/swapping
* pinksale, dxsale automatic contribution
* token price converter and updater from lp pair
#### **crygo/div_finder**
Golang code which can scan the Binance Smart Chain blockchain for contracts with specific function signatures. It processes around 400 blocks/sec and outputs a list of contract addresses with the creation block timestamps.
#### **pumpit**
Trading bot for the KuCoin exchange written in Golang. It uses 3 different methods to listen for signals on a designated Telegram channel. When the fastest method is triggered, the trading bot places trailing stop loss orders using the KuCoin API.
#### **utils**
Simple webscraper utilizing Beautiful Soup python package.

### ├── ethernaut 🎮

The ethernaut folder contains my solution codes for Ethernaut, a Web3/Solidity based hacking game.
<br>spoiler alert: If you're currently playing Ethernaut or planning to, please be aware that the solutions in this folder may spoil your gameplay experience. Explore at your own risk!

### ├── nft 🖼️

The nft folder contains test code for minting legendary NFTs from insecure smart contracts on EVM-based platform, leveraging Web3 Python. The insecurity arises from the minting ID being calculated using the block timestamp. This demonstrates the potential vulnerabilities in NFT creation and serves as a learning resource for secure smart contract development.

### ├── arbitrage 💹

The arbitrage folder contains code for identifying arbitrage opportunities in PancakeSwap tokens. It optimizes the amount of initial investment using SciPy optimization, maximizing profits for swaps up to 3 levels deep, enabling users to discover profitable trading strategies.

### ├── binance_listing_bot 🤖

A python bot that listens for Binance listing announcements using web scraping through proxy lists to avoid poll limits. Upon detecting new listings, the bot is capable of placing orders on Gate.io and identifying the corresponding BSC or ETH contracts for the listed tokens.

### ├── binance_trader 📈

Automated trading during the launch of new tokens on Binance Launchpool with the option to logging tick data for later analysis.

### ├── cryptobot 🧪

Experimental code for compressing candlestick data using an autoencoder neural network. It includes a custom data generator for feeding the TensorFlow network.

### ├── data_download 📊

Multithreaded data grabber for fetching Binance historical tick and kline data. Since it may take hours for the server to generate a download link after a request, this code manages the entire process, handling the waiting and downloading steps for you.

### ├── scripts 🛠️

Various short utility scripts, including data plotting and preprocessing tools. As crypto tick data can occupy significant amount of storage space, this folder also features a compression test code that compares different compression methods and storage types, as well as explores database storage possibilities for efficient data management.

### └── 3rd_party 📚

This folder contains links to other GitHub repositories that provide tools and scripts for fetching real-time data from multiple cryptocurrency exchanges. These resources can be used to collect and store market data locally for further analysis and processing.

<br><br>
## ⚠️ Disclaimer  ⚠️
Please note that the contents of this repository are for informational purposes only. Nothing in this repo should be considered financial or investment advice. Cryptocurrencies and smart contracts involve a high level of risk, and you should always conduct your own research and due diligence before participating in any crypto-related activities. The author of this repository is not responsible for any losses, damages, or adverse consequences that may result from the use of the information, tools, or resources provided herein.