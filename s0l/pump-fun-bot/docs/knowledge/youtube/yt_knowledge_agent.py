import os
from pathlib import Path
import datetime
import glob

from agno.agent import Agent, RunResponse
from agno.models.openai import OpenAIChat
from agno.models.google import Gemini
from rich.pretty import pprint

from yt_knowledge_models import ExtractedKnowledge
from yt_knowledge_prompt import (
    KNOWLEDGE_EXTRACTION_AGENT_DESCRIPTION,
    KNOWLEDGE_EXTRACTION_AGENT_PROMPT,
)
from dotenv import load_dotenv

load_dotenv()
# Define the root directory for subtitles
subtitles_root = Path("docs/knowledge/youtube/subtitles")
output_dir = Path("docs/knowledge/youtube/subtitles_summary")

# Collect all transcription files from each subdirectory
sub_dirs = [d for d in subtitles_root.iterdir() if d.is_dir()]
files_by_dir = {d.name: sorted([f for f in d.glob("*.txt")], reverse=True) for d in sub_dirs}
max_files = max(len(files) for files in files_by_dir.values()) if files_by_dir else 0

# Interleave the processing of files
for i in range(max_files):
    for dir_name, files in files_by_dir.items():
        if i < len(files):
            file_path = files[i]
            source_file = str(file_path.relative_to(subtitles_root))

            # model = Gemini(id="gemini-2.5-pro")
            model = OpenAIChat(id="gpt-5-mini")
            # model = OpenAIChat(id="gpt-4.1")
            # model = OpenAIChat(id="gpt-5")
            
            # Create the output directory structure
            relative_dir = file_path.relative_to(subtitles_root).parent
            current_output_dir = output_dir / relative_dir
            current_output_dir.mkdir(parents=True, exist_ok=True)

            # Generate the output file name
            output_filename = f"{file_path.stem}_{model.id}.json"
            output_file = current_output_dir / output_filename
            
            if os.path.exists(output_file):
                print(f"Output file {output_file} already exists, skipping processing.")
                continue

            print(f"Processing {source_file}...")

            with open(file_path, "r", encoding="utf-8") as f:
                transcription_text = f.read()

            yt_knowledge_agent = Agent(
                model=model,
                context={
                    "source_file": source_file,
                    "transcription_text": transcription_text,
                },
                description=KNOWLEDGE_EXTRACTION_AGENT_DESCRIPTION,
                instructions=KNOWLEDGE_EXTRACTION_AGENT_PROMPT,
                response_model=ExtractedKnowledge,
                add_state_in_messages=True,
                debug_mode=False
            )

            run_response: RunResponse = yt_knowledge_agent.run(
                "Analyze the provided transcription and generate the output."
            )

            # The content of the response is the Pydantic model instance
            yt_knowledge_model: ExtractedKnowledge = run_response.content

            # Serialize the Pydantic model to a JSON string
            knowledge_json_str = yt_knowledge_model.model_dump_json(indent=2)

            # Write the serialized model to the output file
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(knowledge_json_str)

            print(f"Successfully created {output_file} with knowledge from {source_file}")