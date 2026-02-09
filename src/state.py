"""
State schema and Pydantic models for the deep research agent.
"""

from datetime import datetime
from typing import Annotated, Literal, Optional

from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages
from pydantic import BaseModel, Field
from typing_extensions import NotRequired, TypedDict


def merge_question_answers(
    existing: dict[str, "QuestionAnswer"], new: dict[str, "QuestionAnswer"]
) -> dict[str, "QuestionAnswer"]:
    """Reducer: merge answers from parallel researchers."""
    merged = existing.copy() if existing else {}
    if new:
        merged.update(new)
    return merged


def merge_compressed_findings(
    existing: dict[str, str], new: dict[str, str]
) -> dict[str, str]:
    """Reducer: merge compressed findings from parallel researchers."""
    merged = existing.copy() if existing else {}
    if new:
        merged.update(new)
    return merged


class ReportPreferences(BaseModel):
    """User's preferences for the report, parsed from natural language."""
    research_question: str = Field(description="The core research question to answer")
    style: str = Field(default="general", description="Report style: academic, technical, executive, comparative, general")
    focus_areas: list[str] = Field(default_factory=list, description="Specific topics/aspects to focus on")
    audience: str = Field(default="general", description="Target audience: student, professional, general, expert")
    constraints: str = Field(default="", description="Any constraints mentioned (deadline, length, etc.)")


class ResearchState(TypedDict):
    """Complete state for the research agent."""

    messages: Annotated[list[BaseMessage], add_messages]
    original_query: NotRequired[str]

    # Parsed from user's natural language request
    report_preferences: NotRequired[Optional["ReportPreferences"]]

    research_plan: NotRequired[Optional["ResearchPlan"]]
    question_answers: NotRequired[Annotated[dict[str, "QuestionAnswer"], merge_question_answers]]
    compressed_findings: NotRequired[Annotated[dict[str, str], merge_compressed_findings]]
    current_iteration: NotRequired[int]  # Tracks re-research iterations (max 2)
    agent_analysis: NotRequired[Optional["AgentAnalysis"]]
    final_report: NotRequired[str]

    # Routing control from reflection (max 2 iterations)
    next_step: NotRequired[Literal["create_tasks", "compile"]]


# Research Plan Models

class SubQuestion(BaseModel):
    """A specific question to research."""
    question_id: str
    question: str
    search_strategy: str
    importance: str  # critical, important, supporting


class ResearchPlan(BaseModel):
    """Question decomposition."""
    main_question: str
    sub_questions: list[SubQuestion]


# Research Finding Models

class SourceMetadata(BaseModel):
    """Source with metadata and content."""
    id: str
    url: str
    title: str
    full_content: str
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class Finding(BaseModel):
    """A research finding with evidence."""
    claim: str
    evidence: str
    source_ids: list[str]
    confidence: str  # high, medium, low


class QuestionAnswer(BaseModel):
    """Structured answer to a sub-question."""
    question_id: str
    question: str
    answer: str
    key_findings: list[Finding]
    sources: list[SourceMetadata]
    confidence: str  # high, medium, low
    completeness: str  # complete, partial, insufficient


# Agent Reflection Models

class WeakAnswer(BaseModel):
    """A weak answer needing improvement."""
    question_id: str
    issue: str
    suggestion: str


class AgentAnalysis(BaseModel):
    """Agent's analysis of research quality."""
    overall_assessment: Literal["strong", "adequate", "needs_improvement"] = Field(
        description="Must be exactly one of: strong, adequate, needs_improvement"
    )
    weak_answers: list[WeakAnswer]
    knowledge_gaps: list[str]
    conflicting_info: list[str]
    suggested_questions: list[str]
    suggested_searches: list[str]
    reasoning: str


