import json
import os
import requests
from datetime import datetime, timezone, timedelta
import time # For potential delays

class BinancePriceFetcher:
    """
    A class to fetch and manage historical cryptocurrency prices from Binance.
    It caches the fetched data locally to avoid repeated API calls.
    """
    BINANCE_API_URL = "https://api.binance.com/api/v3/klines"

    def __init__(self, 
                 symbol: str = 'SOLUSDT', 
                 interval: str = '1d', 
                 start_date_str: str = '2021-01-01', 
                 cache_dir: str = 'trader/historical_data/cache'):
        """
        Initializes the BinancePriceFetcher.

        :param symbol: Trading symbol (e.g., 'SOLUSDT')
        :param interval: Kline interval (e.g., '1d' for daily)
        :param start_date_str: Start date in 'YYYY-MM-DD' format (e.g., '2020-04-10')
        :param cache_dir: Directory to store cache files.
        """
        if not symbol or not interval or not start_date_str:
            raise ValueError("Symbol, interval, and start_date_str must be provided.")

        self.symbol = symbol.upper()
        self.interval = interval
        try:
            self.start_dt = datetime.strptime(start_date_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        except ValueError:
            raise ValueError("start_date_str must be in 'YYYY-MM-DD' format.")

        self.cache_dir = cache_dir
        self.cache_file_name = f"binance_{self.symbol.lower()}_{self.interval}_prices.json"
        self.cache_file_path = os.path.join(self.cache_dir, self.cache_file_name)
        
        self.prices = {} # Holds date_str: price
        self.latest_cached_dt = None
        self._load_prices_from_cache_or_fetch()

    def _get_interval_duration_ms(self) -> int:
        """Calculates the duration of the interval in milliseconds."""
        if self.interval.endswith('m'): # minutes
            return int(self.interval[:-1]) * 60 * 1000
        elif self.interval.endswith('h'): # hours
            return int(self.interval[:-1]) * 60 * 60 * 1000
        elif self.interval.endswith('d'): # days
            return int(self.interval[:-1]) * 24 * 60 * 60 * 1000
        elif self.interval.endswith('w'): # weeks
            return int(self.interval[:-1]) * 7 * 24 * 60 * 60 * 1000
        # Note: Binance 'M' (Month) interval is tricky as months have variable days.
        # For '1M', Binance typically aligns it to the start of the UTC month.
        # This simple duration calculation won't be perfect for 'M' if precise end-of-month to start-of-next is needed for pagination.
        # However, for daily and shorter, it's fine. For '1M', relying on fetching < limit is safer.
        elif self.interval.endswith('M'):
             # Approximate for pagination, actual candle times from API are definitive
            return 30 * 24 * 60 * 60 * 1000 # Approximate
        else:
            raise ValueError(f"Unsupported interval format for duration calculation: {self.interval}")


    def _fetch_from_api(self):
        """
        Fetches historical daily prices for the configured symbol and interval from Binance API.
        """
        print(f"Fetching historical {self.symbol} prices ({self.interval}) from Binance API, starting from {self.start_dt.strftime('%Y-%m-%d')}...")
        
        all_prices_fetched = {}
        limit = 1000  # Max klines per request for Binance
        current_start_time_ms = int(self.start_dt.timestamp() * 1000)
        interval_duration_ms = self._get_interval_duration_ms()

        while True:
            params = {
                'symbol': self.symbol,
                'interval': self.interval,
                'startTime': current_start_time_ms,
                'limit': limit
            }
            
            try:
                response = requests.get(self.BINANCE_API_URL, params=params)
                response.raise_for_status() 
                data = response.json()
                
                if not data:
                    print(f"No more data received from Binance API for {self.symbol} starting {datetime.fromtimestamp(current_start_time_ms/1000, tz=timezone.utc)}.")
                    break
                
                fetched_count_this_request = 0
                for kline in data:
                    open_time_ms = kline[0]
                    close_price = float(kline[4]) # Close price
                    
                    dt_object = datetime.fromtimestamp(open_time_ms / 1000, tz=timezone.utc)
                    if self.interval.endswith('d') or self.interval.endswith('w') or self.interval.endswith('M'):
                        date_str = dt_object.strftime('%Y-%m-%d')
                    else: # Finer granularity for hours, minutes
                        date_str = dt_object.strftime('%Y-%m-%d %H:%M')

                    all_prices_fetched[date_str] = close_price
                    fetched_count_this_request += 1

                last_kline_open_time_ms = data[-1][0]
                last_kline_dt = datetime.fromtimestamp(last_kline_open_time_ms/1000, tz=timezone.utc)
                print(f"Fetched {fetched_count_this_request} klines for {self.symbol}. Last kline time: {last_kline_dt.strftime('%Y-%m-%d %H:%M:%S UTC')}")

                if fetched_count_this_request < limit:
                    print(f"Reached the end of available historical data for {self.symbol} (or current date).")
                    break
                
                current_start_time_ms = last_kline_open_time_ms + interval_duration_ms
                
                # Optional: Be polite to the API
                time.sleep(0.1) # 100ms delay

            except requests.exceptions.HTTPError as http_err:
                print(f"HTTP error fetching data for {self.symbol} from Binance API: {http_err}")
                if response is not None:
                    print(f"Response status: {response.status_code}, Response text: {response.text}")
                break # Stop fetching on HTTP error
            except requests.exceptions.RequestException as e:
                print(f"Request error fetching data for {self.symbol} from Binance API: {e}")
                break # Stop fetching on other request errors
            except json.JSONDecodeError as e:
                print(f"Error decoding JSON for {self.symbol} from Binance API: {e}")
                if response is not None:
                    print(f"Response text: {response.text}")
                break # Stop fetching

        if all_prices_fetched:
            print(f"Successfully fetched {len(all_prices_fetched)} price points for {self.symbol}.")
            self.prices.update(all_prices_fetched) # Update internal prices
            self._update_latest_cached_dt()
            self._save_prices_to_cache()
        else:
            print(f"No new price data was fetched for {self.symbol}.")


    def _load_prices_from_cache_or_fetch(self):
        """
        Loads historical prices from the local cache file.
        If the file doesn't exist or is empty, fetches prices and saves them.
        """
        if os.path.exists(self.cache_file_path):
            try:
                with open(self.cache_file_path, 'r') as f:
                    self.prices = json.load(f)
                if self.prices:
                    # print(f"Loaded {len(self.prices)} price points for {self.symbol} from {self.cache_file_path}")
                    self._update_latest_cached_dt()
                    # Optional: Add logic here to check if cache is stale and needs updating
                    # For example, if the last date in cache is much older than today for a '1d' interval.
                    return
                else:
                    print(f"Cache file {self.cache_file_path} is empty. Fetching from API.")
            except json.JSONDecodeError:
                print(f"Error decoding JSON from cache file {self.cache_file_path}. Re-fetching.")
            except Exception as e:
                print(f"Error loading cache file {self.cache_file_path}: {e}. Re-fetching.")
        
        # If cache doesn't exist, is empty, or failed to load:
        print(f"Cache file not found or invalid: {self.cache_file_path}. Fetching prices for {self.symbol}.")
        self._fetch_from_api()

    def _save_prices_to_cache(self):
        """Saves the current prices to the cache file."""
        if not self.prices:
            print(f"No prices to save for {self.symbol}.")
            return

        try:
            # Ensure the cache directory exists
            if self.cache_dir:
                 os.makedirs(self.cache_dir, exist_ok=True)
            
            with open(self.cache_file_path, 'w') as f:
                json.dump(self.prices, f, indent=4)
            print(f"Prices for {self.symbol} saved to {self.cache_file_path}")
        except IOError as e:
            print(f"Error saving prices to cache file {self.cache_file_path}: {e}")
        except Exception as e:
            print(f"An unexpected error occurred while saving cache: {e}")


    def _update_latest_cached_dt(self):
        """Updates the latest_cached_dt attribute from the current prices."""
        if not self.prices:
            self.latest_cached_dt = None
            return

        sorted_dates = sorted(self.prices.keys())
        if sorted_dates:
            latest_date_str = sorted_dates[-1]
            try:
                # Handle both date and datetime formats
                if len(latest_date_str) > 10: # 'YYYY-MM-DD HH:MM'
                    self.latest_cached_dt = datetime.strptime(latest_date_str, '%Y-%m-%d %H:%M').replace(tzinfo=timezone.utc)
                else: # 'YYYY-MM-DD'
                    self.latest_cached_dt = datetime.strptime(latest_date_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
            except ValueError:
                 print(f"Warning: Could not parse latest date string '{latest_date_str}' from cache.")
                 self.latest_cached_dt = None


    def get_price(self, target_dt: datetime) -> float | None:
        """
        Receives a datetime object and returns the price for that day.
        Uses pre-fetched daily prices and updates cache if needed.

        :param target_dt: A datetime object for the desired date.
        :return: The close price for that date as a float, or None if not found.
        """
        if not isinstance(target_dt, datetime):
            print(f"Error: target_dt must be a datetime object, but got {type(target_dt)}")
            return None

        # Ensure target_dt is timezone-aware (UTC) for consistent comparison
        if target_dt.tzinfo is None:
            target_dt = target_dt.replace(tzinfo=timezone.utc)
        else:
            target_dt = target_dt.astimezone(timezone.utc)
        
        # Format the date string based on the interval
        if self.interval.endswith('d') or self.interval.endswith('w') or self.interval.endswith('M'):
            date_str = target_dt.strftime('%Y-%m-%d')
            # For daily+ intervals, compare only the date part
            comparison_target = target_dt.date()
            cached_comparison = self.latest_cached_dt.date() if self.latest_cached_dt else None
        else: # Finer granularity for hours, minutes
            # Truncate the datetime to the floor of its interval before lookup
            # For minutes, the strftime format already truncates seconds and microseconds, so no change needed.
            if self.interval.endswith('h'):
                target_dt = target_dt.replace(minute=0, second=0, microsecond=0)
            date_str = target_dt.strftime('%Y-%m-%d %H:%M')
            comparison_target = target_dt
            cached_comparison = self.latest_cached_dt
        
        if self.latest_cached_dt and comparison_target > cached_comparison:
                print(f"Requested date {date_str} is newer than latest cached date {self.latest_cached_dt.strftime('%Y-%m-%d %H:%M')}. Updating prices...")
                self.update_prices_to_latest()
                # After updating, the requested price might now be in the cache.

        # Attempt to get the price from the potentially updated cache
        price = self.prices.get(date_str)

        if price is None:
            # print(f"Warning: {self.symbol} price not found for date {date_str}. Returning None.")
            pass # Less verbose, can be enabled if needed
        return price

    def update_prices_to_latest(self):
        """
        Fetches the latest prices since the last entry in the cache up to the current date.
        This is useful for daily updates.
        """
        if not self.prices:
            print(f"No existing prices for {self.symbol}. Performing initial fetch.")
            self._fetch_from_api()
            return

        sorted_dates = sorted(self.prices.keys())
        if not sorted_dates:
            print(f"Price cache for {self.symbol} is empty. Performing initial fetch.")
            self._fetch_from_api()
            return
            
        last_cached_dt = self.latest_cached_dt
        if not last_cached_dt:
             print("Could not determine last cached date. Re-fetching all.")
             self._fetch_from_api()
             return

        # Determine the next timestamp to fetch from based on interval
        # This can be simplified; for now, let's keep it basic
        if self.interval.endswith('d'):
            next_day_to_fetch_dt = (last_cached_dt + timedelta(days=1))
        elif self.interval.endswith('h'):
            next_day_to_fetch_dt = (last_cached_dt + timedelta(hours=1))
        elif self.interval.endswith('m'):
            next_day_to_fetch_dt = (last_cached_dt + timedelta(minutes=1))
        else:
            # Default for 'w', 'M' etc. - can be refined.
            next_day_to_fetch_dt = (last_cached_dt + timedelta(days=1))

        if next_day_to_fetch_dt >= datetime.now(timezone.utc):
            print(f"Price data for {self.symbol} is up to date ({self.latest_cached_dt.strftime('%Y-%m-%d %H:%M')}). No new data to fetch.")
            return
        
        print(f"Updating {self.symbol} prices from {next_day_to_fetch_dt.strftime('%Y-%m-%d %H:%M:%S')}...")
        
        # Temporarily set self.start_dt for the fetch operation
        original_start_time_ms = int(self.start_dt.timestamp() * 1000)
        self.start_dt = next_day_to_fetch_dt
        self._fetch_from_api() # This will append to self.prices and save
        self.start_dt = datetime.fromtimestamp(original_start_time_ms / 1000, tz=timezone.utc) # Restore original start_dt
        print(f"Update for {self.symbol} complete.")


if __name__ == '__main__':
    # --- Configuration for Solana (SOLUSDT) ---
    sol_symbol = "SOLUSDT"
    sol_interval = "1d"  # Daily prices
    
    try:
        # Create an instance for Solana
        sol_fetcher = BinancePriceFetcher(
            symbol=sol_symbol,
            interval=sol_interval,
        )

        # Example usage:
        example_dt_sol = datetime.strptime('2025-03-25', '%Y-%m-%d')
        price_sol = sol_fetcher.get_price(example_dt_sol)
        if price_sol is not None:
            print(f"\n{sol_fetcher.symbol} price on {example_dt_sol.date()}: {price_sol}")
        else:
            print(f"\n{sol_fetcher.symbol} price not found for {example_dt_sol.date()}")

    except ValueError as ve:
        print(f"Configuration Error: {ve}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")