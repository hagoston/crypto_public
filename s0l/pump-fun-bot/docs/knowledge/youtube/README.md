# YouTube Knowledge Extraction Pipeline

This directory contains a set of Python scripts designed to build a knowledge base from YouTube video transcripts. The process is broken down into three main stages:

1.  **Transcript Grabbing**: Download video transcripts from specified YouTube channels.
2.  **Knowledge Agent**: Process each transcript with an LLM agent to extract structured information.
3.  **Knowledge Merging**: Consolidate the extracted information from all videos into a single, coherent knowledge base.

## 1. Transcript Grabber (`yt_transcript_grabber.py`)

This script is responsible for fetching the transcripts of the latest videos from a predefined list of YouTube channels.

### How it Works:
-   It takes a list of YouTube channel URLs.
-   For each channel, it uses `yt-dlp` to download the subtitles/transcripts for the most recent videos.
-   The transcripts are saved as plain text files (`.txt`) into the `docs/knowledge/youtube/subtitles/<ChannelName>/` directory.
-   The script can be configured to download transcripts for a single video, an entire channel, or discover content based on a search query.

### Usage:
```bash
uv run python docs/knowledge/youtube/yt_transcript_grabber.py
```
The script is pre-configured to download transcripts from a list of channels specified at the bottom of the file.

## 2. Knowledge Agent (`yt_knowledge_agent.py`)

This script processes the downloaded transcripts one by one. It uses a Large Language Model (LLM) agent to read each transcript and extract structured knowledge from it.

### How it Works:
-   It scans the `docs/knowledge/youtube/subtitles/` directory for any new transcript files that haven't been processed yet.
-   For each transcript, it invokes an LLM agent (e.g., GPT-4, Gemini).
-   The agent's task is to summarize the content and structure it into a JSON format according to a predefined Pydantic model (`ExtractedKnowledge`). This ensures the output is consistent.
-   The resulting JSON files are saved in `docs/knowledge/youtube/subtitles_summary/<ChannelName>/`, with one JSON file generated per transcript.

### Usage:
```bash
uv run python docs/knowledge/youtube/yt_knowledge_agent.py
```

## 3. Merge Knowledge (`yt_merge_knowledge.py`)

The final step is to combine all the individual JSON knowledge files into a single, master document. This script handles the consolidation and de-duplication of information.

### How it Works:
-   It loads all the individual `.json` files from the `docs/knowledge/youtube/subtitles_summary/` directory.
-   It uses another LLM agent to intelligently merge the information from these files in batches.
-   The agent combines similar strategies, tools, and concepts, resolving redundancies and creating a unified view of the knowledge.
-   The final, consolidated knowledge base is saved as `docs/knowledge/youtube/master_knowledge.json`.

### Usage:
```bash
uv run python docs/knowledge/youtube/yt_merge_knowledge.py