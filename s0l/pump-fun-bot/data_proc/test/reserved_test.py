import os, sys
import asyncio
import mplfinance as mpf
import matplotlib.pyplot as plt
import numpy as np
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from token_data_fetcher import TokenDataFetcher
from sol_price import BinancePriceFetcher


async def main():
    # fetcher
    fetcher = TokenDataFetcher()

    # get data
    mint = "5NPrivft1grvqQAFpm3VUP3aHZgtfG7x8QJf7tBKpump"
    df = await fetcher.fetch_pumpfun_amm_raw_data(mint_address=mint)

    # df.iloc[0] ==
    #    tsz               2025-04-14 05:37:09.336254+00:00
    #    slot                                     333346810
    #    is_buy                                        True
    #    amount_in                                930000000
    #    amount_out                          32262851600387
    #    base_reserves                          30930000000
    #    token_reserves                    1040737148399613

    # convert to ohlcv for visualization

    # Filter out small/erroneous trades (where both amounts are <= 1)
    min_amount = 1000  # Minimum trade amount threshold
    valid_trades = (df['amount_in'] > min_amount) & (df['amount_out'] > min_amount)
    df = df[valid_trades].copy()
    
    # Effective Price = amount_in / amount_out
    #   sol - lamports
    #   token - 6 decimal
    # Price = (base reserves / 10⁹) ÷ (token reserves / 10⁶)
    SOL_2_LAMPORTS = 1_000_000_000
    TOKEN_DECIMAL = 1_000_000
    TOTAL_SUPPLY = 1_000_000_000
    
    df['effective_price'] = np.where(df['is_buy'], df['amount_in'] / df['amount_out'], df['amount_out'] / df['amount_in'] )
    df['effective_price'] *= TOKEN_DECIMAL / SOL_2_LAMPORTS

    df['marginal_price'] = (df['base_reserves']) / (df['token_reserves'])
    df['marginal_price'] *= TOKEN_DECIMAL / SOL_2_LAMPORTS

    # convert to mcap
    df['effective_price'] *= TOTAL_SUPPLY
    df['marginal_price'] *= TOTAL_SUPPLY

    # convert to $ with solana price on that particular day
    sol_price_fetcher = BinancePriceFetcher()
    sol_2_usd = sol_price_fetcher.get_price(df.iloc[0].tsz)
    df['effective_price'] *= sol_2_usd
    df['marginal_price'] *= sol_2_usd

    # Convert to OHLCV - resample by time (1min default)
    granularity = '1s'
    df.set_index('tsz', inplace=True)


    ohlc_effective = df['effective_price'].resample(granularity, closed='left', label='left').ohlc()
    ohlc_marginal = df['marginal_price'].resample(granularity, closed='left', label='left').ohlc()
    
    # Create figure with two subplots
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16,9), sharex=True)
    
    # Set title for the top plot
    ax1.set_title(f'{mint} {granularity} Effective MCap')
    # Plot effective price on top
    mpf.plot(ohlc_effective,
            type='candle',
            style='charles',
            ax=ax1,
            # title parameter removed
            ylabel='Price')
    
    # Set title for the bottom plot
    ax2.set_title(f'{mint} {granularity} Marginal MCap')
    # Plot marginal price on bottom
    mpf.plot(ohlc_marginal,
            type='candle',
            style='charles',
            ax=ax2,
            # title parameter removed
            ylabel='Price')
    
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    asyncio.run(main())