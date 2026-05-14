import os
import sys
import polars as pl
import numpy as np
import pandas as pd
import argparse
import pandas_ta as ta
from datetime import timedelta

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from trader.data.data_loader import DataLoader
from utils.logger_factory import get_logger

log = get_logger('gen_training_data')

def resample_to_candles(df: pl.DataFrame, timeframe='5s') -> pd.DataFrame:
    """
    Resamples tick data to candles.
    """
    # Convert to pandas for easier resampling with OHLC
    pdf = df.to_pandas()
    pdf.set_index('timestamp', inplace=True)
    
    # Resample
    ohlc = pdf['price'].resample(timeframe).ohlc()
    volume = pdf['quantity'].resample(timeframe).sum()
    buy_vol = pdf[pdf['is_buy']]['quantity'].resample(timeframe).sum()
    count = pdf['price'].resample(timeframe).count()
    
    candles = pd.concat([ohlc, volume, buy_vol, count], axis=1)
    candles.columns = ['open', 'high', 'low', 'close', 'volume', 'buy_volume', 'trade_count']
    
    # Forward fill price (if no trades, price stays same)
    candles['close'] = candles['close'].ffill()
    candles['open'] = candles['open'].fillna(candles['close'])
    candles['high'] = candles['high'].fillna(candles['close'])
    candles['low'] = candles['low'].fillna(candles['close'])
    
    # Fill volume with 0
    candles['volume'] = candles['volume'].fillna(0)
    candles['buy_volume'] = candles['buy_volume'].fillna(0)
    candles['trade_count'] = candles['trade_count'].fillna(0)
    
    return candles




def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Computes technical indicators and market structure features.
    """
    # 1. Log Returns (custom)
    df['log_ret'] = np.log(df['close'] / df['close'].shift(1))
    
    # 2. Volatility (custom)
    df['volatility'] = df['log_ret'].rolling(12).std()  # 1 min
    
    # 3. TA indicators (pandas_ta)
    df['rsi'] = ta.rsi(df['close'], length=14)
    df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    
    # 4. Volume features (custom)
    df['vol_ma'] = df['volume'].rolling(12).mean()
    df['rel_vol'] = df['volume'] / (df['vol_ma'] + 1e-9)
    df['buy_ratio'] = df['buy_volume'] / (df['volume'] + 1e-9)
    
    # 5. Trend (TA SMAs)
    df['sma_fast'] = ta.sma(df['close'], length=12)
    df['sma_slow'] = ta.sma(df['close'], length=24)
    df['trend'] = np.where(df['sma_fast'] > df['sma_slow'], 1, -1)
    
    # 6. VWAP (TA, true volume-weighted)
    df['vwap'] = ta.vwap(df['high'], df['low'], df['close'], df['volume'])
    df['dist_vwap'] = (df['close'] - df['vwap']) / (df['vwap'] + 1e-9)
    
    return df.dropna()

def generate_labels(df: pd.DataFrame, horizon_candles=30, target_pct=0.05, stop_pct=0.01) -> pd.DataFrame:
    """
    Generates binary labels for scalping.
    Target: Price hits +target_pct within horizon_candles BEFORE hitting -stop_pct.
    """
    df = df.copy() # Avoid SettingWithCopyWarning
    labels = []
    
    # Convert to numpy for speed
    close = df['close'].values
    high = df['high'].values
    low = df['low'].values
    
    n = len(df)
    
    for i in range(n):
        if i + horizon_candles >= n:
            labels.append(0)
            continue
            
        entry_price = close[i]
        tp_price = entry_price * (1 + target_pct)
        sl_price = entry_price * (1 - stop_pct)
        
        # Look forward
        window_high = np.max(high[i+1 : i+1+horizon_candles])
        window_low = np.min(low[i+1 : i+1+horizon_candles])
        
        # Check if we hit TP
        hit_tp = window_high >= tp_price
        
        # Check if we hit SL
        hit_sl = window_low <= sl_price
        
        if hit_tp and not hit_sl:
            labels.append(1) # Success
        elif hit_tp and hit_sl:
            # Hit both. Did we hit TP first?
            # This is hard to know with OHLC candles. 
            # Conservative approach: Assume SL hit first if both hit in same window.
            # Or check index of high vs low? (Too complex for simple loop)
            # Let's assume FAIL if SL is hit at all.
            labels.append(0)
        else:
            labels.append(0)
            
    df['target'] = labels
    return df

def process_mint(mint: str, dl: DataLoader, horizon_candles: int = 30, target_pct: float = 0.05, stop_pct: float = 0.01):
    """
    Process a single mint: Load -> Resample -> Feature Eng -> Label -> Save
    """
    try:
        # Load Data
        lf = dl.load_trades_for_mint(mint)
        if lf is None:
            return None
            
        # Collect (might be large, but per-mint should fit in memory)
        df = lf.collect()
        if len(df) < 100: # Skip tiny tokens
            return None
            
        # Resample
        candles = resample_to_candles(df, timeframe='5s')
        if len(candles) < 60: # Need enough history for indicators
            return None
            
        # Features
        features = compute_features(candles)
        
        # Labels (Target: +5% in 150s, SL: -1% -> 5x Risk/Reward)
        labeled = generate_labels(features, horizon_candles=horizon_candles, target_pct=target_pct, stop_pct=stop_pct)
        
        # Add mint column
        labeled['mint'] = mint
        
        return labeled
        
    except Exception as e:
        log.error(f"Error processing {mint}: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description='Generate training data for neural sniper')
    parser.add_argument('--target_pct', type=float, default=0.05, help='Target profit percentage (default 5%)')
    parser.add_argument('--stop_pct', type=float, default=0.01, help='Stop loss percentage (default 1%)')
    parser.add_argument('--horizon_candles', type=int, default=30, help='Prediction horizon in candles (default 30 / 150s)')
    parser.add_argument('--output_path', type=str, default=os.path.join(project_root, 'training_data_5s.parquet'), help='Output parquet path')
    parser.add_argument('--max_mints', type=int, default=200, help='Maximum number of mints to process (default 200)')
    args = parser.parse_args()
    log.info(f"Config: target_pct={args.target_pct:.1%}, stop_pct={args.stop_pct:.1%}, horizon={args.horizon_candles} candles ({args.horizon_candles*5}s), max_mints={args.max_mints}")
    data_dir = os.path.join(project_root, 'trader/historical_data')
    dl = DataLoader(data_dir)
    
    # Get list of all mints (from metadata or scan trades)
    # For now, let's scan the trades directory to find unique mints?
    # Or just load a big chunk and group by mint.
    # Better: Use metadata file if available.
    
    meta = dl.load_token_metadata()
    all_mints = list(meta.keys())
    
    log.info(f"Found {len(all_mints)} mints in metadata.")
    
    all_data = []
    
    # Process top 50 mints for now to test pipeline
    # In production, we'd process all or a large sample
    # Let's try to find "active" mints first?
    # For this script, let's just take the first 100 mints
    
    processed_count = 0
    for mint in all_mints[:args.max_mints]:
        log.info(f"Processing {mint}...")
        df = process_mint(mint, dl, args.horizon_candles, args.target_pct, args.stop_pct)
        if df is not None and len(df) > 0:
            all_data.append(df)
            processed_count += 1
            
    if not all_data:
        log.error("No data generated.")
        return
        
    # Combine
    full_df = pd.concat(all_data)
    
    # Save
    output_path = args.output_path
    full_df.to_parquet(output_path)
    
    log.info(f"Saved training data to {output_path}")
    log.info(f"Total Samples: {len(full_df)}")
    log.info(f"Class Balance: {full_df['target'].value_counts(normalize=True)}")

if __name__ == "__main__":
    main()
