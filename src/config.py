"""
Configuration schema for the deep research agent.

Supports runtime configuration of:
- Model selection
- Research parameters
"""

from pydantic import BaseModel, Field


class AgentConfig(BaseModel):
    """Runtime configuration for the research agent."""

    # Model
    model: str = Field(default="gpt-4o", description="OpenAI model")
    temperature: float = Field(default=0.1, description="LLM temperature")

    # Search - OPTIMIZED for cost/quality balance
    max_search_results: int = Field(default=5, description="Results per query")
    max_questions: int = Field(default=10, description="Max sub-questions for comprehensive coverage")

    # Research depth
    max_iterations: int = Field(default=2, description="Max reflection iterations")
    chars_per_source: int = Field(default=12000, description="Chars per source for compression")


def get_config(config: dict) -> AgentConfig:
    """Extract AgentConfig from LangGraph config dict."""
    configurable = config.get("configurable", {})

    return AgentConfig(
        model=configurable.get("model", "gpt-4o"),
        temperature=configurable.get("temperature", 0.1),
        max_search_results=configurable.get("max_search_results", 5),
        max_questions=configurable.get("max_questions", 10),
        max_iterations=configurable.get("max_iterations", 2),
        chars_per_source=configurable.get("chars_per_source", 12000),
    )
