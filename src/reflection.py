"""
Reflection node: Analyzes research quality and suggests improvements.

Evaluates completed research against quality criteria and identifies:
- Weak answers needing more research
- Knowledge gaps in coverage
- Conflicting information across sources
"""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI

from .config import AgentConfig, get_config
from .prompts import REFLECTION_SYSTEM_PROMPT
from .state import AgentAnalysis, QuestionAnswer, ResearchPlan, ResearchState


class ReflectionAnalyzer:
    """
    Analyzer that critically evaluates research quality.

    Provides proactive suggestions for improvement, identifies weak answers,
    knowledge gaps, and conflicting information.
    """

    def __init__(self, config: AgentConfig | None = None):
        """
        Initialize the analyzer with an LLM.

        Args:
            config: AgentConfig with model settings
        """
        self.config = config or AgentConfig()
        self.llm = ChatOpenAI(model=self.config.model, temperature=0)

    def analyze_research(
        self, plan: ResearchPlan, answers: dict[str, QuestionAnswer]
    ) -> AgentAnalysis:
        """
        Analyze research quality and provide suggestions.

        Args:
            plan: The research plan
            answers: Dict of question_id -> QuestionAnswer

        Returns:
            AgentAnalysis with assessment and suggestions
        """
        # Format current research for analysis
        research_summary = self._format_research_summary(plan, answers)

        # Get structured analysis
        messages = [
            SystemMessage(content=REFLECTION_SYSTEM_PROMPT),
            HumanMessage(
                content=f"Research Plan and Current Findings:\n\n{research_summary}\n\n"
                f"Provide a critical analysis of this research with specific suggestions."
            ),
        ]

        structured_llm = self.llm.with_structured_output(AgentAnalysis)
        analysis = structured_llm.invoke(messages)

        return analysis

    def format_analysis_message(self, analysis: AgentAnalysis) -> str:
        """
        Format analysis as a human-readable message.

        Args:
            analysis: The agent's analysis

        Returns:
            Formatted markdown string
        """
        message_parts = [
            "# Agent Analysis of Research Quality\n",
            f"**Overall Assessment**: {analysis.overall_assessment}\n",
        ]

        # Weak answers
        if analysis.weak_answers:
            message_parts.append(f"\n## ⚠️ Weak Answers ({len(analysis.weak_answers)})\n")
            for wa in analysis.weak_answers:
                message_parts.append(
                    f"- **Question {wa.question_id}**: {wa.issue}\n"
                    f"  *Suggestion*: {wa.suggestion}\n"
                )
        else:
            message_parts.append("\n## ✅ No Weak Answers Identified\n")

        # Knowledge gaps
        if analysis.knowledge_gaps:
            message_parts.append(f"\n## 🔍 Knowledge Gaps ({len(analysis.knowledge_gaps)})\n")
            for gap in analysis.knowledge_gaps:
                message_parts.append(f"- {gap}\n")
        else:
            message_parts.append("\n## ✅ No Major Knowledge Gaps\n")

        # Conflicts
        if analysis.conflicting_info:
            message_parts.append(
                f"\n## ⚡ Conflicting Information ({len(analysis.conflicting_info)})\n"
            )
            for conflict in analysis.conflicting_info:
                message_parts.append(f"- {conflict}\n")

        # Suggestions
        message_parts.append("\n## 💡 Agent's Suggestions\n")

        if analysis.suggested_questions:
            message_parts.append("\n**Suggested Additional Questions:**\n")
            for sq in analysis.suggested_questions:
                message_parts.append(f"- {sq}\n")

        if analysis.suggested_searches:
            message_parts.append("\n**Suggested Searches:**\n")
            for ss in analysis.suggested_searches:
                message_parts.append(f"- {ss}\n")

        message_parts.append(f"\n**Reasoning**: {analysis.reasoning}\n")

        message_parts.append("\n---\n**Next**: Human review with agent insights\n")

        return "".join(message_parts)

    # Helper methods

    def _format_research_summary(
        self, plan: ResearchPlan, answers: dict[str, QuestionAnswer]
    ) -> str:
        """Format research for LLM analysis."""
        summary_parts = [f"# Research on: {plan.main_question}\n"]
        summary_parts.append("\n## Research Questions and Answers\n")

        # Flat structure
        for sq in plan.sub_questions:
            answer = answers.get(sq.question_id)
            summary_parts.append(f"\n### Question {sq.question_id}: {sq.question}\n")
            summary_parts.append(f"**Importance**: {sq.importance}\n")

            if answer:
                # Handle both dict and QuestionAnswer objects (state serialization)
                if isinstance(answer, dict):
                    answer_text = answer.get("answer", "")
                    confidence = answer.get("confidence", "unknown")
                    completeness = answer.get("completeness", "unknown")
                    sources = answer.get("sources", [])
                else:
                    answer_text = answer.answer
                    confidence = answer.confidence
                    completeness = answer.completeness
                    sources = answer.sources

                # Show full answer up to 6000 chars (covers most answers completely)
                # No middle markers that confuse the LLM
                answer_preview = answer_text[:6000]
                truncated = "..." if len(answer_text) > 6000 else ""
                summary_parts.append(f"**Answer** ({len(answer_text)} chars, completeness={completeness}):\n{answer_preview}{truncated}\n\n")
                summary_parts.append(
                    f"**Confidence**: {confidence}, "
                    f"**Completeness**: {completeness}, "
                    f"**Sources**: {len(sources)}\n"
                )
            else:
                summary_parts.append("**Status**: Not yet researched\n")

        return "".join(summary_parts)


# ============================================================================
# LangGraph Node Function
# ============================================================================


def reflection_node(state: ResearchState, config: RunnableConfig | None = None) -> dict:
    """
    Analyze research quality and decide: improve or compile.

    Returns suggested_searches that researcher will use directly.
    """
    print("[Reflection] Analyzing research quality...")
    agent_config = get_config(config or {})
    analyzer = ReflectionAnalyzer(config=agent_config)

    plan = state["research_plan"]
    answers = state["question_answers"]
    current_iteration = state.get("current_iteration", 0)

    if isinstance(plan, dict):
        plan = ResearchPlan(**plan)

    analysis = analyzer.analyze_research(plan, answers)
    analysis_message = analyzer.format_analysis_message(analysis)

    # Decide: improve or compile report
    needs_improvement = (
        analysis.overall_assessment == "needs_improvement"
        and analysis.weak_answers
        and current_iteration < agent_config.max_iterations
    )

    next_step = "re_research" if needs_improvement else "compile"
    new_iteration = current_iteration + 1 if needs_improvement else current_iteration

    print(f"[Reflection] Assessment: {analysis.overall_assessment}, weak_answers={len(analysis.weak_answers or [])}, iteration={current_iteration} -> {next_step}")
    if needs_improvement and analysis.suggested_searches:
        print(f"[Reflection] Suggested searches: {analysis.suggested_searches[:3]}")

    return {
        "agent_analysis": analysis,
        "next_step": next_step,
        "current_iteration": new_iteration,
        "messages": [AIMessage(content=analysis_message)],
    }
