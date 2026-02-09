"""
Planner node: Parse user request and decompose into research plan.

This node:
1. Parses natural language to extract research question + report preferences
2. Decomposes into sub-questions for parallel research
"""

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI

from .config import AgentConfig, get_config
from .prompts import PLANNER_EXAMPLE, PLANNER_SYSTEM_PROMPT, get_current_date_context
from .state import ReportPreferences, ResearchPlan, ResearchState


class Planner:
    """Planner parses requests and creates research plans."""

    def __init__(self, config: AgentConfig | None = None):
        self.config = config or AgentConfig()
        self.llm = ChatOpenAI(model=self.config.model, temperature=0)

    def parse_request(self, user_input: str) -> ReportPreferences:
        """
        Parse natural language request to extract research question and preferences.

        Example input:
        "Who's a better NBA player between Shai and Luka? I want a very technical
        report for my school project tomorrow and the report should focus on
        scoring efficiency, defense, and leadership."

        Returns:
            ReportPreferences with extracted info
        """
        prompt = f"""Parse this user request and extract the research details.

USER REQUEST:
{user_input}

Extract:
1. research_question: The core question to research (clean, focused)
2. style: Report style - one of: academic, technical, executive, comparative, general
   - "technical" = detailed stats, metrics, analysis
   - "academic" = scholarly, citations, methodology
   - "comparative" = comparing entities side by side
   - "executive" = brief, key points, recommendations
   - "general" = balanced, readable
3. focus_areas: Specific topics to emphasize (as a list)
4. audience: Who is this for? student, professional, general, expert
5. constraints: Any mentioned constraints (deadline, length, format)

If something isn't specified, use sensible defaults based on context."""

        messages = [
            SystemMessage(content="You extract structured information from natural language requests."),
            HumanMessage(content=prompt),
        ]

        structured_llm = self.llm.with_structured_output(ReportPreferences)
        preferences = structured_llm.invoke(messages)
        print(f"[Planner] Parsed request: {preferences.research_question[:60]}...")
        return preferences

    def plan(self, preferences: ReportPreferences) -> ResearchPlan:
        """
        Create research plan based on parsed preferences.

        Args:
            preferences: Parsed user preferences including focus areas

        Returns:
            ResearchPlan with sub-questions
        """
        # Build context about what to focus on
        focus_context = ""
        if preferences.focus_areas:
            focus_context = "\n\nIMPORTANT FOCUS AREAS (prioritize these):\n" + \
                           "\n".join(f"- {area}" for area in preferences.focus_areas)

        audience_context = f"\nTARGET AUDIENCE: {preferences.audience}"
        if preferences.audience == "student":
            audience_context += " (explain concepts clearly, educational tone)"
        elif preferences.audience == "expert":
            audience_context += " (assume domain knowledge, focus on nuance)"

        messages = [
            SystemMessage(content=PLANNER_SYSTEM_PROMPT.format(date_context=get_current_date_context())),
            SystemMessage(content=f"Example structure:\n\n{PLANNER_EXAMPLE}"),
            HumanMessage(
                content=f"Create a research plan for: {preferences.research_question}"
                f"{focus_context}"
                f"{audience_context}"
            ),
        ]

        structured_llm = self.llm.with_structured_output(ResearchPlan)
        plan = structured_llm.invoke(messages)

        # Limit questions to save API calls (focus on quality over quantity)
        if len(plan.sub_questions) > self.config.max_questions:
            # Keep only the most important questions
            critical = [q for q in plan.sub_questions if q.importance == "critical"]
            important = [q for q in plan.sub_questions if q.importance == "important"]
            supporting = [q for q in plan.sub_questions if q.importance == "supporting"]

            # Prioritize critical, then important, then supporting
            plan.sub_questions = (critical + important + supporting)[:self.config.max_questions]

        return plan


def planner_node(state: ResearchState, config: RunnableConfig | None = None) -> dict:
    """
    LangGraph node that parses request and creates research plan.

    Flow:
    1. Parse natural language → ReportPreferences
    2. Create research plan based on preferences
    """
    agent_config = get_config(config or {})
    planner = Planner(config=agent_config)

    # Get query from state or messages
    query = state.get("original_query")

    if not query:
        messages = state.get("messages", [])
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage) or (hasattr(msg, 'type') and msg.type == 'human'):
                query = msg.content if hasattr(msg, 'content') else str(msg)
                break

    if not query:
        raise ValueError("No query found in state.")

    # Step 1: Parse the request
    preferences = planner.parse_request(query)

    # Step 2: Create research plan
    research_plan = planner.plan(preferences)

    print(f"[Planner] Created plan with {len(research_plan.sub_questions)} sub-questions")

    return {
        "research_plan": research_plan,
        "report_preferences": preferences,
        "original_query": query,
    }
