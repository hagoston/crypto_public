import os
import glob
import json
from pathlib import Path
from typing import Dict, List
from collections import defaultdict

from yt_knowledge_models import ExtractedKnowledge, MergedKnowledge, MemeCoinStrategy, Tool, ProcessedFile, FeatureRequirement
from yt_knowledge_prompt import MERGE_KNOWLEDGE_AGENT_PROMPT

from agno.agent import Agent, RunResponse
from agno.models.openai import OpenAIChat
from agno.models.google import Gemini


def load_all_extracted_knowledge(base_dir: str) -> List[ExtractedKnowledge]:
    """
    Load all ExtractedKnowledge JSON files from subtitles_summary.
    """
    knowledge_list = []
    for path in glob.glob(os.path.join(base_dir, "**/*.json"), recursive=True):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            knowledge_list.append(ExtractedKnowledge(**data))
    return knowledge_list


def consolidate_knowledge_with_llm(knowledge_list: List[ExtractedKnowledge], batch_size: int = 10) -> MergedKnowledge:
    """
    Consolidate ExtractedKnowledge using an LLM agent with MERGE_KNOWLEDGE_AGENT_PROMPT
    in batches. Takes n documents at a time and merges them with the running master.
    """
    #model = OpenAIChat(id="gemini-2.5-pro")
    model = Gemini(id="gemini-2.5-pro")
    merged_model: MergedKnowledge = MergedKnowledge()  # start empty

    for i in range(0, len(knowledge_list), batch_size):
        batch = knowledge_list[i:i + batch_size]
        inputs = [k.model_dump()["strategies"] for k in batch]

        agent = Agent(
            model=model,
            context={
                "extracted_strategies_batch": inputs,
                "current_merged": merged_model.model_dump(),
            },
            description="Incrementally merge ExtractedKnowledge batch into an updated MergedKnowledge output.",
            instructions=MERGE_KNOWLEDGE_AGENT_PROMPT,
            response_model=MergedKnowledge,
            add_state_in_messages=True,
            debug_mode=False,
        )

        run_response: RunResponse = agent.run("Merge the current batch of strategies with the existing master.")
        merged_model = run_response.content

        # save each intermediate merged_model to timestamped file
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = "docs/knowledge/youtube/subtitles_summary"
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, f"{ts}_merged_knowledge.json")
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(merged_model.model_dump_json(indent=2))
        print(f"Intermediate merged knowledge saved to {output_file}")

    return merged_model


def main():
    base_dir = "docs/knowledge/youtube/subtitles_summary"
    output_file = "docs/knowledge/youtube/master_knowledge.json"

    knowledge_list = load_all_extracted_knowledge(base_dir)

    merged = consolidate_knowledge_with_llm(knowledge_list)

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(merged.model_dump_json(indent=2))

    print(f"Merged knowledge saved to {output_file}")


if __name__ == "__main__":
    main()