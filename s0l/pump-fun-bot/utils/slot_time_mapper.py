import asyncio
import json
import sys, os
from typing import Dict, List, Optional, Tuple
from solana.rpc.async_api import AsyncClient
import time
from datetime import datetime, timezone # Added timezone
# Add numpy and matplotlib imports for testing
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

# Ensure pandas is available for the test function
try:
    import pandas as pd
except ImportError:
    pd = None # Handle case where pandas might not be installed

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))
from logger_factory import get_logger
log = get_logger(__name__)

# Constants
DEFAULT_CACHE_FILENAME = "slot_time_cache.json"
# How many slots around an estimated second boundary to fetch for refinement
INTERPOLATION_REFINEMENT_WINDOW = 5
# Maximum number of additional slots to fetch for refinement per batch
MAX_REFINEMENT_FETCHES = 10

class SlotTimeMapper:
    """
    Handles fetching Solana block times via RPC, caching results,
    and interpolating timestamps for given slots. Includes cache persistence
    and refined interpolation. Optimized for pumpfun token data patterns.
    """
    def __init__(self, rpc_endpoint: str, cache_file_path: str = DEFAULT_CACHE_FILENAME):
        """
        Initializes the mapper with an RPC endpoint and cache file path.

        Args:
            rpc_endpoint: The Solana RPC endpoint URL.
            cache_file_path: Path to the file for loading/saving the slot cache.
                             Defaults to 'slot_time_cache.json' in the same directory.
        """
        if not rpc_endpoint:
            raise ValueError("RPC endpoint must be provided.")
        self.rpc_endpoint = rpc_endpoint
        # Determine cache file path relative to this script's directory if not absolute
        if not os.path.isabs(cache_file_path):
             script_dir = os.path.dirname(os.path.abspath(__file__))
             self.cache_file_path = os.path.join(script_dir, cache_file_path)
        else:
             self.cache_file_path = cache_file_path

        self.client = AsyncClient(rpc_endpoint)
        self.slot_cache: Dict[int, Optional[int]] = {} # slot -> Unix timestamp (seconds)
        self._load_cache() # Load cache on initialization
        log.info(f"SlotTimeMapper initialized with endpoint: {rpc_endpoint}, cache: {self.cache_file_path}")
        # Keep track of slots fetched in the current session for testing/analysis
        self._session_fetched_slots = set()
        # Store reference data for validation
        self.reference_data = None

    def _load_cache(self):
        """Loads the slot cache from the specified JSON file."""
        if not self.cache_file_path or not os.path.exists(self.cache_file_path):
            log.info(f"Cache file not found at {self.cache_file_path}. Starting with empty cache.")
            return

        try:
            with open(self.cache_file_path, 'r') as f:
                # Load cache, converting string keys back to integers, ignore None values from file
                loaded_data = json.load(f)
                self.slot_cache = {int(k): v for k, v in loaded_data.items() if v is not None}
                log.info(f"Loaded {len(self.slot_cache)} valid entries from cache file: {self.cache_file_path}")
        except (json.JSONDecodeError, IOError, ValueError) as e:
            log.error(f"Error loading cache file {self.cache_file_path}: {e}. Starting with empty cache.")
            self.slot_cache = {} # Reset cache on error

    def _save_cache(self):
        """Saves the current slot cache to the specified JSON file."""
        if not self.cache_file_path:
            log.warning("Cache file path not set. Cannot save cache.")
            return

        try:
            # Ensure directory exists
            cache_dir = os.path.dirname(self.cache_file_path)
            if cache_dir and not os.path.exists(cache_dir):
                 os.makedirs(cache_dir, exist_ok=True)
                 log.info(f"Created cache directory: {cache_dir}")

            # Only save non-None values
            cache_to_save = {str(k): v for k, v in self.slot_cache.items() if v is not None}
            with open(self.cache_file_path, 'w') as f:
                json.dump(cache_to_save, f, indent=2)
            log.debug(f"Saved {len(cache_to_save)} entries to cache file: {self.cache_file_path}")
        except IOError as e:
            log.error(f"Error saving cache file {self.cache_file_path}: {e}")

    async def close_client(self, save_cache: bool = True):
        """Closes the underlying HTTPX client and optionally saves the cache."""
        if self.client:
            is_connected = hasattr(self.client, '_http') and self.client._http is not None
            if is_connected:
                await self.client.close()
                log.info("SlotTimeMapper's Solana AsyncClient closed.")
            else:
                log.debug("SlotTimeMapper's Solana AsyncClient was already closed or not initialized.")

        if save_cache:
            self._save_cache()

    async def _fetch_block_time(self, slot: int) -> Optional[int]:
        """Fetches block time from RPC or cache. Records fetched slots."""
        # Return cached value immediately if it exists (even if None previously failed)
        if slot in self.slot_cache:
            return self.slot_cache[slot]

        # Mark as fetched for this session *before* the RPC call
        self._session_fetched_slots.add(slot)
        start_time = time.monotonic()
        try:
            response = await self.client.get_block_time(slot)
            timestamp = response.value if response and response.value is not None else None
            self.slot_cache[slot] = timestamp # Cache the result (even if None)
            elapsed = time.monotonic() - start_time
            if timestamp is None:
                 log.warning(f"getBlockTime({slot}) returned None. Request took {elapsed:.3f}s.")
            return timestamp
        except Exception as e:
            elapsed = time.monotonic() - start_time
            log.error(f"Error fetching block time for slot {slot}: {e}. Request took {elapsed:.3f}s.")
            self.slot_cache[slot] = None # Cache failure explicitly
            return None

    async def _fetch_batch_block_times(self, slots_to_fetch: List[int]) -> Dict[int, Optional[int]]:
        """Fetches block times for a list of slots, utilizing cache."""
        results = {}
        needs_fetch = sorted(list(set(s for s in slots_to_fetch if s not in self.slot_cache))) # Unique, sorted list of slots NOT in cache

        # Populate results with cached values first
        for slot in slots_to_fetch:
            if slot in self.slot_cache:
                results[slot] = self.slot_cache[slot]

        if not needs_fetch:
            return results # All requested slots were already cached

        log.debug(f"Fetching block times for {len(needs_fetch)} uncached slots...")
        # Use asyncio.gather to run fetches concurrently
        tasks = [self._fetch_block_time(slot) for slot in needs_fetch]
        fetched_timestamps = await asyncio.gather(*tasks)

        # Update results dict with newly fetched values
        for slot, timestamp in zip(needs_fetch, fetched_timestamps):
            results[slot] = timestamp # _fetch_block_time already updated cache and _session_fetched_slots

        return results


    async def get_interpolated_timestamps(self, slots: List[int]) -> Dict[int, Optional[float]]:
        """
        Gets estimated timestamps for a list of unique, sorted slots using refined interpolation.
        Uses 400ms/slot as initial estimate and validates against reference data if available.
        """
        if not slots:
            return {}
        # Reset session fetch tracker for this call
        self._session_fetched_slots = set()

        results: Dict[int, Optional[float]] = {}
        min_slot = slots[0]
        max_slot = slots[-1]

        log.debug(f"Interpolating timestamps for {len(slots)} slots ({min_slot} to {max_slot}).")

        # --- Step 1: Fetch boundaries (will use cache if available) ---
        initial_fetch_slots = list(set([min_slot, max_slot]))
        boundary_times = await self._fetch_batch_block_times(initial_fetch_slots)
        ts_min_raw = boundary_times.get(min_slot)
        ts_max_raw = boundary_times.get(max_slot)

        # If we have at least one boundary, use it for fast estimation
        if ts_min_raw is not None or ts_max_raw is not None:
            base_slot = min_slot if ts_min_raw is not None else max_slot
            base_ts = ts_min_raw if ts_min_raw is not None else ts_max_raw
            fast_estimates = await self.get_fast_estimate_timestamps(slots, base_slot, base_ts)
            
            # Validate against reference data if available
            if self.reference_data is not None:
                validated = await self.validate_against_reference(slots, fast_estimates)
                for slot, ts in validated.items():
                    results[slot] = ts
            else:
                results.update(fast_estimates)

        # --- Step 2: Perform initial interpolation for refinement candidate selection ---
        initial_estimates: Dict[int, Optional[float]] = {}
        can_interpolate_initially = False
        if min_slot == max_slot:
            initial_estimates = {slot: float(ts_min_raw) if ts_min_raw is not None else None for slot in slots}
            can_interpolate_initially = ts_min_raw is not None
        elif ts_min_raw is not None and ts_max_raw is not None:
            # Apply +0.5 adjustment *only* for the initial estimation phase
            ts_min_adj = ts_min_raw + 0.5
            ts_max_adj = ts_max_raw + 0.5
            delta_ts = float(ts_max_adj - ts_min_adj)
            delta_slots = float(max_slot - min_slot)

            if delta_slots > 0:
                can_interpolate_initially = True
                for slot in slots:
                    ratio = (slot - min_slot) / delta_slots
                    initial_estimates[slot] = float(ts_min_adj) + ratio * delta_ts

        # --- Step 3: Identify critical slots for refinement (prioritizing uncached) ---
        refinement_candidates_set = set()
        if can_interpolate_initially and len(slots) > 2:
            last_estimated_second = None
            for i, slot in enumerate(slots):
                est_ts = initial_estimates.get(slot)
                if est_ts is None: continue
                current_estimated_second = int(est_ts)

                if last_estimated_second is not None and current_estimated_second != last_estimated_second:
                    start_idx = max(0, i - INTERPOLATION_REFINEMENT_WINDOW)
                    end_idx = min(len(slots), i + INTERPOLATION_REFINEMENT_WINDOW)
                    for j in range(start_idx, end_idx):
                         if 0 <= j < len(slots):
                              refinement_candidates_set.add(slots[j])
                last_estimated_second = current_estimated_second

        # Filter candidates: exclude boundaries and keep only those NOT in cache
        initial_refinement_candidates = sorted(list(refinement_candidates_set - set(initial_fetch_slots)))

        needs_fetching_candidates = [
            slot for slot in initial_refinement_candidates
            if slot not in self.slot_cache # Only consider slots not already cached
        ]

        # Apply fetch limit
        if len(needs_fetching_candidates) > MAX_REFINEMENT_FETCHES:
            step = max(1, len(needs_fetching_candidates) // MAX_REFINEMENT_FETCHES)
            final_refinement_list = needs_fetching_candidates[::step][:MAX_REFINEMENT_FETCHES]
            log.warning(f"Too many uncached refinement candidates ({len(needs_fetching_candidates)}), fetching only {len(final_refinement_list)} slots.")
        else:
            final_refinement_list = needs_fetching_candidates

        # --- Step 4: Fetch actual times for selected refinement slots ---
        all_fetched_points_map: Dict[int, Optional[int]] = {}
        all_fetched_points_map.update(boundary_times) # Start with boundaries

        if final_refinement_list:
            log.debug(f"Fetching {len(final_refinement_list)} refinement slots: {final_refinement_list}")
            refinement_times = await self._fetch_batch_block_times(final_refinement_list)
            all_fetched_points_map.update(refinement_times)
        else:
            log.debug("No additional refinement slots needed fetching (all candidates cached or limit 0).")


        # Filter out None values and sort points for piecewise interpolation
        valid_fetched_points: List[Tuple[int, int]] = sorted([
            (slot, ts) for slot, ts in all_fetched_points_map.items() if ts is not None
        ])

        # --- Step 5: Perform piecewise linear interpolation ---
        if not valid_fetched_points:
            log.error("No valid timestamps could be fetched, even for boundaries. Cannot interpolate.")
            return {slot: None for slot in slots}

        log.debug(f"Performing piecewise interpolation using {len(valid_fetched_points)} fetched points.")
        results = {}
        point_idx = 0
        for slot_idx, slot in enumerate(slots):
            # Find the segment [p1, p2] that brackets the current slot
            while point_idx + 1 < len(valid_fetched_points) and valid_fetched_points[point_idx + 1][0] <= slot:
                point_idx += 1

            if point_idx + 1 < len(valid_fetched_points):
                p1_slot, p1_ts = valid_fetched_points[point_idx]
                p2_slot, p2_ts = valid_fetched_points[point_idx + 1]

                if p1_slot <= slot <= p2_slot:
                    if p1_slot == p2_slot:
                        results[slot] = float(p1_ts)
                    else:
                        delta_ts_segment = float(p2_ts - p1_ts)
                        delta_slots_segment = float(p2_slot - p1_slot)
                        if delta_slots_segment > 0 and delta_ts_segment >= 0:
                             ratio = (slot - p1_slot) / delta_slots_segment
                             estimated_ts = float(p1_ts) + ratio * delta_ts_segment
                             results[slot] = estimated_ts
                        elif delta_slots_segment > 0 and delta_ts_segment < 0:
                             log.warning(f"Timestamp decreased within segment [{p1_slot}({p1_ts}), {p2_slot}({p2_ts})]. Assigning start time {p1_ts} to slot {slot}.")
                             results[slot] = float(p1_ts)
                        else:
                             results[slot] = float(p1_ts)
                elif slot < p1_slot:
                     log.warning(f"Slot {slot} is before the start of its identified segment {p1_slot}. Assigning segment start time {p1_ts}.")
                     results[slot] = float(p1_ts)
                else:
                     log.error(f"Unexpected state: Slot {slot} is after its identified segment ends at {p2_slot}. Assigning None.")
                     results[slot] = None
            else:
                last_slot, last_ts = valid_fetched_points[-1]
                if slot == last_slot:
                    results[slot] = float(last_ts)
                else:
                    log.warning(f"Slot {slot} is after the last valid fetched point {last_slot}. Assigning its time {last_ts}.")
                    results[slot] = float(last_ts)

            if slot not in results:
                log.error(f"Interpolation logic failed to assign a value for slot {slot}. Setting to None.")
                results[slot] = None

        if len(results) != len(slots):
             log.warning(f"Final interpolation result count ({len(results)}) mismatch with requested slot count ({len(slots)}).")
             for slot in slots:
                 if slot not in results: results[slot] = None

        return results
    async def get_fast_estimate_timestamps(self, slots: List[int], base_slot: int, base_ts: float) -> Dict[int, float]:
        """
        Fast estimation using 400ms/slot assumption from a known base point.
        Args:
            slots: List of slots to estimate timestamps for
            base_slot: A slot with known timestamp
            base_ts: The known timestamp for base_slot (seconds)
        Returns:
            Dictionary mapping slots to estimated timestamps
        """
        return {slot: base_ts + (slot - base_slot) * 0.4 for slot in slots}

    def set_reference_data(self, reference_df: pd.DataFrame):
        """Set reference OHLCV data for validation purposes."""
        self.reference_data = reference_df

    async def validate_against_reference(self, slots: List[int], estimated_timestamps: Dict[int, float]) -> Dict[int, float]:
        """
        Validate estimated timestamps against reference data and return adjusted timestamps.
        Args:
            slots: List of slots being estimated
            estimated_timestamps: Initial timestamp estimates
        Returns:
            Dictionary of adjusted timestamps
        """
        if self.reference_data is None:
            log.warning("No reference data set for validation")
            return estimated_timestamps

        # Find nearest reference points to validate against
        adjusted = {}
        for slot in slots:
            est_ts = estimated_timestamps.get(slot)
            if est_ts is None:
                continue
            
            # Find closest reference timestamp
            idx = (self.reference_data.index - est_ts).abs().idxmin()
            ref_ts = self.reference_data.index[idx].timestamp()
            
            # If difference > 1 second, adjust towards reference
            if abs(est_ts - ref_ts) > 1.0:
                adjusted[slot] = (est_ts + ref_ts) / 2  # Simple average
                log.debug(f"Adjusted slot {slot} timestamp from {est_ts} towards reference {ref_ts}")
            else:
                adjusted[slot] = est_ts
        
        return adjusted


# Example Usage (for testing purposes)
async def _test():
    # Setup logging for testing
    log_test = get_logger('SlotTimeMapperTest', level='DEBUG') # Use specific test logger

    # --- Configuration ---
    rpc_url = "https://api.mainnet-beta.solana.com" # Use a reliable RPC
    slots_file = "slots.npy" # Path to your numpy slots file
    output_plot_file = "interpolation_test_plot.png"
    # Use the default cache file path defined in the constants
    cache_file = os.path.join(os.path.dirname(__file__), DEFAULT_CACHE_FILENAME)
    log_test.info(f"Using main cache file for test: {cache_file}")
    
    # Load reference data if available
    reference_file = "test/5yKCpxBVgnyKxsL6KPkiQzPTW7XAc8Mf8QsiWkzepump_00.json"
    reference_data = None
    if os.path.exists(reference_file):
        with open(reference_file) as f:
            data = json.load(f)
            reference_data = pd.DataFrame({
                'open': data['o'],
                'high': data['h'],
                'low': data['l'],
                'close': data['c'],
                'volume': data['v']
            }, index=pd.to_datetime(data['t'], unit='ms'))

    mapper = None # Initialize mapper to None
    initial_cache_size = 0
    try:
        # --- Load Slots ---
        if not os.path.exists(slots_file):
            log_test.error(f"Slots file not found: {slots_file}")
            return
        try:
            slots_to_test = np.load(slots_file)
            slots_to_test = sorted(list(set(slots_to_test.astype(int))))
            if not slots_to_test:
                log_test.error("No valid slots loaded from file.")
                return
            log_test.info(f"Loaded {len(slots_to_test)} unique slots from {slots_file} ({slots_to_test[0]} to {slots_to_test[-1]})")
        except Exception as e:
            log_test.error(f"Error loading slots from {slots_file}: {e}")
            return

        # --- Initialize Mapper (using the main cache file) ---
        mapper = SlotTimeMapper(rpc_endpoint=rpc_url, cache_file_path=cache_file)
        initial_cache_size = len(mapper.slot_cache)
        log_test.info(f"Initial cache size: {initial_cache_size}")

        # Set reference data if available
        if reference_data is not None:
            mapper.set_reference_data(reference_data)
            log_test.info(f"Loaded reference data with {len(reference_data)} points")

        # --- Perform Interpolation ---
        log_test.info("Starting timestamp interpolation...")
        start_interp_time = time.monotonic()
        interpolated_timestamps_map = await mapper.get_interpolated_timestamps(slots_to_test)
        interp_duration = time.monotonic() - start_interp_time
        log_test.info(f"Interpolation finished in {interp_duration:.3f} seconds.")
        log_test.info(f"RPC calls made in this session: {len(mapper._session_fetched_slots)}")

        # --- Prepare Data for Analysis ---
        results_list = []
        missing_count = 0
        for slot in slots_to_test:
            ts = interpolated_timestamps_map.get(slot)
            results_list.append({'slot': slot, 'interpolated_ts': ts})
            if ts is None:
                missing_count += 1
        if missing_count > 0:
            log_test.warning(f"{missing_count} slots could not be interpolated.")

        if pd is None:
            log_test.error("Pandas library is required for test analysis and plotting. Please install it.")
            return

        results_df = pd.DataFrame(results_list).dropna(subset=['interpolated_ts'])
        if results_df.empty:
            log_test.error("No valid interpolated timestamps generated.")
            return

        results_df = results_df.sort_values('slot').reset_index(drop=True)
        results_df['ts_delta'] = results_df['interpolated_ts'].diff()
        results_df['slot_delta'] = results_df['slot'].diff()
        results_df['dt_per_slot'] = results_df.apply(lambda row: row['ts_delta'] / row['slot_delta'] if row['slot_delta'] is not None and row['slot_delta'] > 0 else np.nan, axis=1)

        # --- Extract Fetched Anchor Points for this run ---
        session_fetched_slots_in_range = mapper._session_fetched_slots.intersection(set(slots_to_test))
        fetched_slots_sorted = sorted(list(session_fetched_slots_in_range))

        anchor_points = []
        second_mismatches = 0
        for slot in fetched_slots_sorted:
            fetched_ts = mapper.slot_cache.get(slot)
            interpolated_ts = interpolated_timestamps_map.get(slot)
            if fetched_ts is not None and interpolated_ts is not None:
                # Add the actual fetched timestamp (not interpolated) for plotting anchors
                anchor_points.append({'slot': slot, 'fetched_ts': fetched_ts})
                if int(fetched_ts) != int(interpolated_ts):
                    log_test.warning(f"Second mismatch for fetched slot {slot}: Fetched={fetched_ts}, Interpolated={interpolated_ts:.4f}")
                    second_mismatches += 1
        anchor_df = pd.DataFrame(anchor_points)
        log_test.info(f"Identified {len(anchor_df)} anchor points fetched via RPC during this run.")
        if second_mismatches > 0:
             log_test.warning(f"Found {second_mismatches} second-level mismatches between fetched and interpolated values at anchor points.")
        else:
             log_test.info("Interpolated timestamps match fetched timestamps at the second level for all anchor points.")


        # --- Plotting ---
        log_test.info(f"Generating plot: {output_plot_file}")
        fig, axes = plt.subplots(3, 1, figsize=(15, 15), sharex=True)
        fig.suptitle(f'Slot Time Interpolation Analysis ({slots_to_test[0]} to {slots_to_test[-1]})', fontsize=16)

        # Plot 1: Timestamp vs Slot
        ax1 = axes[0]
        ax1.plot(results_df['slot'], results_df['interpolated_ts'], label='Interpolated Timestamp', marker='.', linestyle='-', markersize=2, zorder=2)
        if not anchor_df.empty:
            ax1.scatter(anchor_df['slot'], anchor_df['fetched_ts'], color='red', marker='o', s=50, label=f'Fetched Anchor Points ({len(anchor_df)})', zorder=5)
        ax1.set_ylabel('Unix Timestamp (float)')
        ax1.legend()
        ax1.grid(True)
        ax1.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.2f'))

        # Plot 2: Timestamp Deltas
        ax2 = axes[1]
        ax2.plot(results_df['slot'][1:], results_df['ts_delta'][1:], label='Delta Timestamp (dt)', marker='.', linestyle='-', markersize=3)
        ax2.axhline(0.4, color='r', linestyle='--', label='Expected ~0.4s')
        ax2.set_ylabel('Time Delta (s)')
        ax2.legend()
        ax2.grid(True)
        ax2.set_ylim(bottom=0, top=max(1.0, results_df['ts_delta'].max() * 1.1 if pd.notna(results_df['ts_delta'].max()) and results_df['ts_delta'].max() > 0 else 1.0))

        # Plot 3: dt / ds
        ax3 = axes[2]
        valid_dt_ds = results_df[['slot', 'dt_per_slot']].dropna()
        ax3.plot(valid_dt_ds['slot'], valid_dt_ds['dt_per_slot'], label='dt / ds', marker='.', linestyle='-', markersize=3)
        ax3.axhline(0.4, color='r', linestyle='--', label='Expected ~0.4s/slot')
        ax3.set_xlabel('Slot Number')
        ax3.set_ylabel('Time Delta per Slot (s/slot)')
        ax3.legend()
        ax3.grid(True)
        ax3.set_ylim(bottom=0, top=max(1.0, valid_dt_ds['dt_per_slot'].max() * 1.1 if pd.notna(valid_dt_ds['dt_per_slot'].max()) and valid_dt_ds['dt_per_slot'].max() > 0 else 1.0))

        plt.tight_layout(rect=[0, 0.03, 1, 0.97])
        #plt.savefig(output_plot_file)
        log_test.info(f"Plot saved to {output_plot_file}")
        plt.show() # Keep commented out for non-interactive runs
        plt.close(fig)

    except Exception as e:
        log_test.exception("An error occurred during the test execution.")
    finally:
        # Ensure client is closed and cache saved, even if mapper initialization failed
        if mapper is not None:
            await mapper.close_client(save_cache=True) # Save the main cache
            final_cache_size = len(mapper.slot_cache)
            log_test.info(f"Test finished, mapper closed. Final cache size: {final_cache_size} (added {final_cache_size - initial_cache_size})")
        else:
            log_test.info("Test finished, mapper was not initialized.")

if __name__ == "__main__":
    # Add pandas import check for _test
    if pd is None:
         print("Error: Pandas library is required to run the test function.")
         print("Please install it using: pip install pandas")
         sys.exit(1)
    # To run the test: python -m utils.slot_time_mapper
    asyncio.run(_test())