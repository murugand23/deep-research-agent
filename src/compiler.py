"""
Compiler node: Generate final report from pre-compressed findings.

Two-step process:
1. Plan report structure based on actual findings (avoid repetition)
2. Generate sections with specific, non-overlapping content guidance
"""

import re

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from .config import AgentConfig, get_config
from .prompts import get_current_date_context
from .state import ReportPreferences, ResearchPlan, ResearchState, SourceMetadata


class SectionPlan(BaseModel):
    """Plan for a single report section."""
    title: str = Field(description="Section title")
    focus: str = Field(description="What this section should specifically cover - be precise")
    key_points: list[str] = Field(description="3-5 key points to address in this section")
    word_target: int = Field(default=750, description="Target word count per section")


class ReportPlan(BaseModel):
    """Structured plan for the entire report."""
    title: str = Field(description="Report title")
    sections: list[SectionPlan] = Field(description="Ordered list of sections with non-overlapping content")
    total_words: int = Field(default=5500, description="Total target word count")


class ReportCompiler:
    """Report compiler with intelligent planning to avoid repetition."""

    def __init__(self, config: AgentConfig | None = None):
        self.config = config or AgentConfig()
        self.llm = ChatOpenAI(model=self.config.model, temperature=0.3)

    def compile_report(
        self,
        plan: ResearchPlan,
        sources: list[SourceMetadata],
        compressed_findings: dict[str, str],
        preferences: ReportPreferences | None = None,
    ) -> str:
        """Generate report with planning step to avoid repetition."""
        print("[Compiler] Generating final report...")

        # Combine all findings
        all_findings = "\n\n".join(compressed_findings.values())

        # Build source reference
        source_list = "\n".join([
            f"- [{s.id}] {s.title}: {s.url}"
            for s in sources[:50]
        ])

        # STEP 1: Plan the report structure based on actual findings
        report_plan = self._plan_report(plan.main_question, all_findings, preferences)
        print(f"[Compiler] Planned {len(report_plan.sections)} sections")

        # STEP 2: Generate each section with specific guidance
        audience = preferences.audience if preferences else "general"
        style = preferences.style if preferences else "general"

        section_texts = []
        previous_content = ""  # Track what's been written to avoid repetition

        for section_plan in report_plan.sections:

            section_text = self._generate_section(
                main_question=plan.main_question,
                section_plan=section_plan,
                findings=all_findings[:20000],
                source_list=source_list[:3000],
                style=style,
                audience=audience,
                previous_content=previous_content[:2000] if previous_content else "",
            )
            section_texts.append(section_text)
            previous_content += section_text + "\n\n"

        report = "\n\n".join(section_texts)

        # Format citations
        return self._format_citations(report, sources)

    def _plan_report(
        self,
        question: str,
        findings: str,
        preferences: ReportPreferences | None,
    ) -> ReportPlan:
        """Use LLM to plan report structure based on actual findings and user preferences."""

        # Extract all preferences
        style = preferences.style if preferences else "general"
        audience = preferences.audience if preferences else "general reader"
        focus_areas = preferences.focus_areas if preferences and preferences.focus_areas else []
        constraints = preferences.constraints if preferences and preferences.constraints else ""

        # Build preferences section for prompt
        prefs_lines = [f"STYLE: {style}", f"AUDIENCE: {audience}"]
        if focus_areas:
            prefs_lines.append(f"FOCUS AREAS: {', '.join(focus_areas)}")
        if constraints:
            prefs_lines.append(f"USER CONSTRAINTS: {constraints}")
        prefs_section = "\n".join(prefs_lines)

        # Determine target word count from constraints or default
        word_guidance = "7-10 sections, 5000-6000 words total, 500-800 words per section"
        if constraints:
            word_guidance = f"Adjust based on: {constraints}. Default: 7-10 sections, 5000-6000 words."

        prompt = f"""Create a COMPREHENSIVE report structure for this research question:

QUESTION: {question}

USER PREFERENCES:
{prefs_section}

RESEARCH FINDINGS (summarized):
{findings[:12000]}

REPORT STRUCTURE REQUIREMENTS:

1. INTRODUCTION (600-800 words)
   - Context and significance of the topic
   - Key themes that will be explored
   - Current landscape/state of affairs

2. SUBJECT DEEP-DIVES (600-800 words EACH)
   - If comparing entities: dedicate a full section to EACH major subject
   - Include specific data, metrics, statistics in each
   - Use markdown tables for quantitative comparisons

3. ANALYTICAL FRAMEWORK (600-800 words)
   - Advanced metrics or evaluation criteria
   - Methodology for assessment
   - Data-driven analysis with specific numbers

4. CONTEXTUAL FACTORS (500-700 words)
   - External factors affecting the topic
   - Recent developments or changes
   - Constraints, rules, or conditions that matter

5. MULTI-FACETED CONCLUSIONS (600-800 words)
   - Break down conclusions by CATEGORY (not just one verdict)
   - "Best in X", "Leading in Y", "Most impactful for Z"
   - Acknowledge nuance and different perspectives

6. FINAL SYNTHESIS (400-600 words)
   - Overall verdict with clear reasoning
   - Forward-looking implications
   - Key takeaways

LENGTH TARGET: {word_guidance}

CRITICAL RULES:
- Each section covers DIFFERENT content - NO OVERLAP
- Section titles should be SPECIFIC to actual content
- Include markdown tables where data comparisons exist
- Every claim needs [source_id] citations
- Be comprehensive - this is a DEEP research report

Create a plan with DISTINCT sections that achieve 5000-6000 words total:"""

        messages = [
            SystemMessage(content="You are a report structure planner. Create logical, non-repetitive report outlines."),
            HumanMessage(content=prompt),
        ]

        structured_llm = self.llm.with_structured_output(ReportPlan)
        report_plan = structured_llm.invoke(messages)

        return report_plan

    def _generate_section(
        self,
        main_question: str,
        section_plan: SectionPlan,
        findings: str,
        source_list: str,
        style: str,
        audience: str,
        previous_content: str,
    ) -> str:
        """Generate a comprehensive section with detailed analysis."""

        audience_guidance = {
            "student": "Write clearly, explain concepts, educational tone.",
            "expert": "Assume domain knowledge, focus on nuance and advanced analysis.",
            "professional": "Business-appropriate, actionable insights.",
            "general": "Balanced, accessible, engaging.",
        }.get(audience, "")

        key_points_str = "\n".join(f"- {p}" for p in section_plan.key_points)

        prompt = f"""Write a COMPREHENSIVE "{section_plan.title}" section for a deep research report.

RESEARCH QUESTION: {main_question}

SECTION: {section_plan.title}
SPECIFIC FOCUS: {section_plan.focus}
KEY POINTS TO COVER:
{key_points_str}

TARGET LENGTH: {section_plan.word_target} words (DO NOT write less)
AUDIENCE: {audience} - {audience_guidance}

{"ALREADY COVERED (DO NOT REPEAT):" + chr(10) + previous_content[:3000] if previous_content else ""}

RESEARCH FINDINGS:
{findings}

SOURCES:
{source_list}

WRITING REQUIREMENTS:
1. Write COMPREHENSIVE content - aim for {section_plan.word_target} words minimum
2. Include SPECIFIC data: numbers, percentages, dates, rankings
3. Use markdown TABLES when comparing 3+ items with metrics:
   | Item | Metric 1 | Metric 2 | Metric 3 |
   |------|----------|----------|----------|
4. Use [source_id] citations for EVERY factual claim
5. Use ### subheadings to organize content
6. Include direct quotes from experts/sources when available
7. Do NOT repeat content from earlier sections
8. Be analytical - explain WHY data matters, not just WHAT it is

Write the section (start with ## {section_plan.title}):"""

        messages = [
            SystemMessage(content=f"You write detailed {style} research reports. Stay focused on the specific section topic and avoid repeating earlier content.\n{get_current_date_context()}"),
            HumanMessage(content=prompt),
        ]

        response = self.llm.invoke(messages)
        return response.content

    def _format_citations(self, report: str, sources: list[SourceMetadata]) -> str:
        """Convert [source_id] to [N] and add references."""

        used_ids = set(re.findall(r'\[(src_[a-zA-Z0-9]+)\]', report))
        source_map = {s.id: s for s in sources}
        id_to_num = {sid: idx for idx, sid in enumerate(sorted(used_ids), 1)}

        # Replace citations
        def replace(match):
            sid = match.group(1)
            return f"[{id_to_num.get(sid, '?')}]"

        report = re.sub(r'\[(src_[a-zA-Z0-9]+)\]', replace, report)

        # Remove old references section
        report = re.sub(r'\n+##?\s*References?\s*\n.*', '', report, flags=re.DOTALL | re.IGNORECASE)

        # Add formatted references
        if used_ids:
            refs = ["\n\n## References\n\n"]
            for sid in sorted(used_ids, key=lambda x: id_to_num.get(x, 999)):
                num = id_to_num.get(sid)
                source = source_map.get(sid)
                if num and source:
                    refs.append(f"[{num}] [{source.title}]({source.url})\n")
            report += "".join(refs)

        return report

def compiler_node(state: ResearchState, config: RunnableConfig | None = None) -> dict:
    """LangGraph node for report compilation."""

    agent_config = get_config(config or {})
    compiler = ReportCompiler(config=agent_config)

    compressed_findings = state.get("compressed_findings", {})

    # Simple fallback if no compressed findings
    if not compressed_findings:
        for q_id, answer in state.get("question_answers", {}).items():
            if answer:
                compressed_findings[q_id] = f"## {answer.question}\n\n{answer.answer}"

    # Gather sources from question_answers (avoid storing separately)
    all_sources = []
    seen_urls = set()
    for q_id, answer in state.get("question_answers", {}).items():
        if answer and hasattr(answer, "sources"):
            for src in answer.sources or []:
                url = src.url if hasattr(src, "url") else src.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_sources.append(src)

    # Get report preferences from state (parsed from user's request)
    preferences = state.get("report_preferences")

    final_report = compiler.compile_report(
        plan=state["research_plan"],
        sources=all_sources,
        compressed_findings=compressed_findings,
        preferences=preferences,
    )

    return {
        "final_report": final_report,
        "messages": [AIMessage(content=final_report)],
    }
