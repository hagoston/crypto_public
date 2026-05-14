import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path

import webvtt
import yt_dlp


def word_level_vtt_parser(vtt_path: str) -> list[dict[str, str]]:
    """
    Extracts start time and text from a VTT file and returns a list of dictionaries.
    """
    result = []
    time_pattern = r"^(.*) align:start position:0%"

    with open(vtt_path, "r") as f:
        lines = f.readlines()

    for count, line in enumerate(lines):
        time_match = re.match(time_pattern, line)

        if time_match:
            start_match = re.search(r"^(.*) -->", time_match.group(1))
            start_time = start_match.group(1) if start_match else ""

            stop_match = re.search(r"--> (.*)", time_match.group(1))
            stop_time = stop_match.group(1) if stop_match else ""

            sub_titles = lines[count + 1]

            # Prevent duplicate entries
            if result and result[-1]['text'] == sub_titles.strip('\n'):
                # Replace the previous entry with the new one
                result[-1] = {
                    'start_time': start_time,
                    'stop_time': stop_time,
                    'text': sub_titles.strip('\n'),
                }
            else:
                result.append({
                    'start_time': start_time,
                    'stop_time': stop_time,
                    'text': sub_titles.strip('\n'),
                })

    return result


def normal_vtt_parser(vtt_path: str) -> list[dict[str, str]]:
    """
    Parses a VTT file using the webvtt library.
    """
    result = []
    for caption in webvtt.read(vtt_path):
        result.append({
            'start_time': caption.start,
            'stop_time': caption.end,
            'text': caption.text,
        })
    return result


def parse_vtt(vtt_path: str) -> list[dict[str, str]]:
    """
    Tries word-level parsing first, then falls back to normal parsing.
    """
    result = word_level_vtt_parser(vtt_path)
    if not result:
        result = normal_vtt_parser(vtt_path)
    if not result:
        print(f"Error: Failed to parse subtitles for: {vtt_path}")
    return result


def sanitize_filename(filename: str) -> str:
    """
    Removes invalid characters from a filename.
    """
    return re.sub(r'[<>:"/\\|?*]', '_', filename)


def dl_video_transcript(video_id: str, subtitle_dir: Path):
    """
    Downloads, parses, and saves the transcript for a single YouTube video ID.
    """
    video_url = f"https://www.youtube.com/watch?v={video_id}"

    # Check if a file containing the video_id already exists
    if subtitle_dir.exists() and any(video_id in f.name for f in subtitle_dir.glob("*/*") if f.is_file()):
        print(f"Transcript for video ID '{video_id}' already exists. Skipping.")
        return True

    try:
        print(f"Downloading subtitles for: {video_url}")
        with tempfile.TemporaryDirectory() as tmp_dir:
            ydl_opts = {
                'outtmpl': f'{tmp_dir}/%(id)s',
                'writeinfojson': True,
                'writeautomaticsub': True,
                'subtitlesformat': 'vtt',
                'skip_download': True,
                'subtitleslangs': ['en', '-live_chat'],
                'quiet': True,
                'no_warnings': True,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(video_url, download=False)
                ydl.download([video_url])

            items = os.listdir(tmp_dir)
            vtt_files = [os.path.join(tmp_dir, item) for item in items if item.endswith('.vtt')]

            if not vtt_files:
                print(f"Warning: Failed to download subtitles for {video_id}.")
                return False

            data = info_dict
            channel = data.get('channel', 'UnknownChannel')
            fulltitle = data.get('fulltitle', 'UnknownTitle')
            upload_date = data.get('upload_date', 'nodate')

            channel_dir = subtitle_dir / sanitize_filename(channel)
            channel_dir.mkdir(parents=True, exist_ok=True)

            sanitized_title = sanitize_filename(fulltitle)
            output_filename = f"{upload_date}_{sanitized_title}_{video_id}.txt"
            output_path = channel_dir / output_filename

            vtt_json = parse_vtt(vtt_files[0])
            transcript = ""
            for subtitle in vtt_json:
                text = subtitle['text'].strip()
                if text:
                    transcript += f"{text}\n"

            with open(output_path, "w") as f:
                f.write(transcript)

            print(f"Transcript saved to: {output_path}")
            return True

    except Exception as e:
        print(f"Failed to process video: {video_id}\n{e}")
        return False


def dl_channel_transcripts(channel_url: str, max_videos: int = 20):
    """
    Downloads transcripts for the latest videos in a given channel.
    """
    script_dir = Path(__file__).parent
    subtitle_dir = script_dir / "subtitles"

    # Get the list of videos quickly
    ydl_opts_flat = {'quiet': True, 'extract_flat': True, 'skip_download': True}
    with yt_dlp.YoutubeDL(ydl_opts_flat) as ydl:
        try:
            info_dict = ydl.extract_info(channel_url, download=False)
            
            videos_playlist = None
            if 'entries' in info_dict:
                 for entry in info_dict['entries']:
                    if entry and 'title' in entry and 'Videos' in entry['title']:
                        videos_playlist = entry.get('entries')
                        break

            if not videos_playlist:
                print("Could not find a 'Videos' playlist for this channel URL.")
                if 'entries' in info_dict:
                    print(".. using main entries")
                    videos_playlist = info_dict['entries']
                else:
                    return

            print(f"Found {len(videos_playlist)} videos in the 'Videos' tab.")
            
            # Process the first 'max_videos' videos
            for video_entry in videos_playlist[:max_videos]:
                video_id = video_entry['id']
                dl_video_transcript(video_id, subtitle_dir)

        except Exception as e:
            print(f"Could not process channel {channel_url}: {e}")


def discover_and_process_content(query: str, max_results: int = 10):
    """
    Discovers and processes videos based on a search query.
    """
    script_dir = Path(__file__).parent
    subtitle_dir = script_dir / "subtitles"

    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
        'force_generic_extractor': True,
        'skip_download': True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            search_results = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)
            if 'entries' in search_results:
                print(f"Found {len(search_results['entries'])} videos for query '{query}'.")
                for video in search_results['entries']:
                    video_id = video['id']
                    # We need to get video info to check tags
                    info_opts = {'quiet': True}
                    with yt_dlp.YoutubeDL(info_opts) as info_ydl:
                        info = info_ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
                        tags = [tag.lower() for tag in info.get('tags', [])]
                        # Simple check if relevant tags are present
                        if any(t in ['solana', 'meme coin', 'crypto'] for t in tags):
                             print(f"Processing relevant video: {video_id}")
                             dl_video_transcript(video_id, subtitle_dir)
                        else:
                            print(f"Skipping video {video_id} due to irrelevant tags.")
            else:
                print(f"No videos found for query '{query}'.")
        except Exception as e:
            print(f"An error occurred during content discovery: {e}")


def main():
    parser = argparse.ArgumentParser(description="Download YouTube video transcripts for analysis.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--video_id", help="A single YouTube video ID.")
    group.add_argument("--channel_url", help="A YouTube channel URL to process all videos from.")
    group.add_argument("--discover", action="store_true", help="Discover new content related to Solana meme coins.")
    
    args = parser.parse_args()

    script_dir = Path(__file__).parent
    subtitle_dir = script_dir / "subtitles"

    if args.video_id:
        dl_video_transcript(args.video_id, subtitle_dir)
    elif args.channel_url:
        dl_channel_transcripts(args.channel_url)
    elif args.discover:
        discover_and_process_content("Solana meme coin strategy")


if __name__ == "__main__":
    #main()
    
    channels = [
        'https://www.youtube.com/@CoinTalkShow',
        'https://www.youtube.com/@SebOrellana',
        'https://www.youtube.com/@CoskiCrypto',
        'https://www.youtube.com/@KavoTrades',
        'https://www.youtube.com/@riseandgrindeveryday',
        'https://www.youtube.com/@OnChainEdu',
        'https://www.youtube.com/@JackKhye',
        'https://www.youtube.com/@payout.',
        'https://www.youtube.com/@starwifpump',
        'https://www.youtube.com/@AlexChoiCrypto',
        'https://www.youtube.com/@OrangieWEB3',
        'https://www.youtube.com/@HandsomeFinance',
        'https://www.youtube.com/@LeckSol',
        'https://www.youtube.com/@LiamJamesKay'
    ]
    dl_channel_transcripts(channels[0], max_videos = 30)
    