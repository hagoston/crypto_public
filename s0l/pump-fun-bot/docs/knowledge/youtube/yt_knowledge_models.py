from pydantic import BaseModel, Field
from typing import List, Optional

class MemeCoinStrategy(BaseModel):
    """
    Describes a specific meme coin trading strategy.
    """
    name: str = Field(..., description="A unique name for the trading strategy.")
    source_files: List[str] = Field(..., description="List of file paths or sources used to define this strategy.")
    description: str = Field(..., description="A detailed description of the trading strategy, including its logic, rules, and indicators.")

class ProcessedFile(BaseModel):
    """
    Represents a file that has been processed and is referenced in the knowledge base.
    """
    filename: str = Field(..., description="The name of the processed file.")
    description: Optional[str] = Field(None, description="A brief description of the file's content or relevance.")

class Tool(BaseModel):
    """
    Represents a tool or software mentioned.
    """
    name: str = Field(..., description="The name of the tool.")
    description: Optional[str] = Field(None, description="An optional description of the tool.")

class ExtractedKnowledge(BaseModel):
    """
    A container for all knowledge extracted from a source, such as a YouTube video transcription.
    """
    strategies: List[MemeCoinStrategy] = Field(default_factory=list, description="A list of trading strategies derived from the source.")
    tools: List[Tool] = Field(default_factory=list, description="A list of tools (e.g., software, websites) mentioned.")
    processed_files: List[ProcessedFile] = Field(default_factory=list, description="A list of processed files associated with this knowledge.")

class FeatureRequirement(BaseModel):
    """
    Represents an individual on-chain or contextual feature required
    to implement one or more strategies.
    """
    name: str = Field(..., description="The name of the feature (e.g., Holder Count, Market Cap).")
    description: Optional[str] = Field(None, description="Detailed explanation of the feature and how it is used.")
    strategies: List[str] = Field(default_factory=list, description="List of strategy names that rely on this feature.")


class MergedKnowledge(BaseModel):
    """
    Represents the consolidated and merged set of strategies, tools,
    and required features across all YouTube sources.
    """
    strategies: List[MemeCoinStrategy] = Field(default_factory=list, description="Merged unique trading strategies.")
    processed_files: List[str] = Field(default_factory=list, description="The name of the processed file.")
    features: List[FeatureRequirement] = Field(default_factory=list, description="Unique features that must be available across strategies.")
