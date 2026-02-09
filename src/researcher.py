"""
Researcher node: Conduct parallel research on sub-questions using web search.

This node handles searching, extracting findings, and synthesizing answers
for individual sub-questions.
"""

import uuid
from datetime import datetime

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from tavily import TavilyClient

from .config import AgentConfig, get_config
from .prompts import (
    ANSWER_SYNTHESIS_PROMPT,
    COMPRESS_RESEARCH_PROMPT,
    RESEARCHER_SYSTEM_PROMPT,
    get_current_date_context,
)
from .state import Finding, QuestionAnswer, ResearchState, SourceMetadata, SubQuestion


class Researcher:
    """
    Conducts web searches and synthesizes answers for sub-questions.

    Handles the full research lifecycle:
    1. Generate search queries from sub-question
    2. Execute searches via Tavily API
    3. Extract structured findings from results
    4. Synthesize comprehensive answer with citations
    """

    def __init__(self, config: AgentConfig | None = None):
        """
        Initialize the researcher with LLM and search client.

        Args:
            config: AgentConfig with model, search settings, etc.
                   If None, uses defaults.
        """
        self.config = config or AgentConfig()
        self.llm = ChatOpenAI(
            model=self.config.model,
            temperature=self.config.temperature
        )

        # Initialize search client
        self.search_client = TavilyClient()

    def generate_search_queries(
        self, sub_question: SubQuestion, main_query: str
    ) -> list[str]:
        """
        Generate 3-4 targeted search queries for a sub-question.

        Args:
            sub_question: The question to research
            main_query: The original user query for context

        Returns:
            List of search query strings
        """
        prompt = f"""Generate 3-4 specific search queries to answer this question.

Research Question: {sub_question.question}
Search Strategy: {sub_question.search_strategy}
Main Topic Context: {main_query}

Return ONLY the search queries, one per line, no numbering or formatting."""

        response = self.llm.invoke([HumanMessage(content=prompt)])
        queries = [q.strip() for q in response.content.strip().split("\n") if q.strip()]

        return queries[:4]  # Limit to 4 queries

    def search_tavily(self, query: str, max_results: int | None = None) -> list[dict]:
        """
        Execute Tavily web search (search only, no extract - cheaper).

        Args:
            query: Search query string
            max_results: Maximum number of results (uses config default if None)

        Returns:
            List of search result dicts with snippets
        """
        if max_results is None:
            max_results = self.config.max_search_results

        try:
            response = self.search_client.search(
                query=query,
                max_results=max_results,
                search_depth="basic",
                include_answer=True,
            )
            return response.get("results", [])
        except (ConnectionError, TimeoutError, ValueError) as e:
            print(f"Tavily search error: {e}")
            return []

    def extract_full_content(self, urls: list[str]) -> dict[str, str]:
        """
        Extract full page content from URLs using Tavily Extract API.

        Call this ONCE per question with the best URLs, not on every search.

        Args:
            urls: List of URLs to extract content from

        Returns:
            Dict mapping URL -> full content
        """
        if not urls:
            return {}

        try:
            response = self.search_client.extract(urls=urls[:10])
            return {
                r.get("url"): r.get("raw_content", "")
                for r in response.get("results", [])
                if r.get("url") and r.get("raw_content")
            }
        except (ConnectionError, TimeoutError, ValueError) as e:
            print(f"Tavily extract error: {e}")
            return {}

    def extract_findings(
        self, search_results: list[dict], sub_question: SubQuestion
    ) -> tuple[list[Finding], list[SourceMetadata]]:
        """
        Extract structured findings from search results.

        Args:
            search_results: Raw Tavily search results
            sub_question: The question being researched

        Returns:
            Tuple of (findings, sources)
        """
        if not search_results:
            return [], []

        all_findings = []
        all_sources = []

        # Create sources and collect content for extraction
        source_contents = []
        for result in search_results:
            content = result.get("full_content") or result.get("content", "")
            source = SourceMetadata(
                id=f"src_{uuid.uuid4().hex[:8]}",
                url=result.get("url", ""),
                title=result.get("title", ""),
                full_content=content,
                timestamp=datetime.now().isoformat(),
            )
            all_sources.append(source)
            # Keep content for finding extraction (limit each to prevent overflow)
            source_contents.append({
                "id": source.id,
                "title": source.title,
                "content": content[:4000] if content else ""
            })

        # Extract findings from ALL sources in one call (more context = better extraction)
        formatted_sources = "\n\n".join([
            f"[{s['id']}] {s['title']}\n{s['content']}"
            for s in source_contents if s['content']
        ])

        messages = [
            SystemMessage(content=f"""You are a research analyst extracting key findings from sources.

For the question: {sub_question.question}

Extract 3-6 SPECIFIC, FACTUAL findings from the sources below. Each finding should:
1. Be a concrete claim with specific data (numbers, names, dates, statistics)
2. Include supporting evidence (quote or paraphrase from source)
3. Reference the source ID [src_xxx]

Format each finding as:
CLAIM: [specific factual claim]
EVIDENCE: [supporting quote or data from source]
SOURCE: [source_id]
CONFIDENCE: [high/medium/low]

---"""),
            HumanMessage(content=f"Sources:\n{formatted_sources}\n\nExtract key findings:"),
        ]

        try:
            response = self.llm.invoke(messages)

            # Parse findings from structured response
            findings_text = response.content
            current_finding = {}

            for line in findings_text.split("\n"):
                line = line.strip()
                if line.startswith("CLAIM:"):
                    if current_finding.get("claim"):
                        # Save previous finding
                        all_findings.append(Finding(
                            claim=current_finding.get("claim", ""),
                            evidence=current_finding.get("evidence", ""),
                            source_ids=current_finding.get("source_ids", []),
                            confidence=current_finding.get("confidence", "medium"),
                        ))
                    current_finding = {"claim": line[6:].strip()}
                elif line.startswith("EVIDENCE:"):
                    current_finding["evidence"] = line[9:].strip()
                elif line.startswith("SOURCE:"):
                    src = line[7:].strip()
                    current_finding["source_ids"] = [src] if src else []
                elif line.startswith("CONFIDENCE:"):
                    conf = line[11:].strip().lower()
                    current_finding["confidence"] = conf if conf in ["high", "medium", "low"] else "medium"

            # Don't forget the last finding
            if current_finding.get("claim"):
                all_findings.append(Finding(
                    claim=current_finding.get("claim", ""),
                    evidence=current_finding.get("evidence", ""),
                    source_ids=current_finding.get("source_ids", []),
                    confidence=current_finding.get("confidence", "medium"),
                ))

        except (KeyError, AttributeError, TypeError) as e:
            print(f"Error extracting findings: {e}")
            # Fallback: create basic findings from sources
            for source in all_sources[:5]:
                if source.full_content:
                    all_findings.append(Finding(
                        claim=source.title,
                        evidence=source.full_content[:500],
                        source_ids=[source.id],
                        confidence="low",
                    ))

        return all_findings, all_sources

    def synthesize_answer(
        self,
        sub_question: SubQuestion,
        findings: list[Finding],
        sources: list[SourceMetadata],
    ) -> QuestionAnswer:
        """
        Synthesize a comprehensive answer from findings.

        Args:
            sub_question: The question being answered
            findings: Extracted findings
            sources: Source metadata

        Returns:
            Complete QuestionAnswer object
        """
        if not findings:
            # No findings - return insufficient answer
            return QuestionAnswer(
                question_id=sub_question.question_id,
                question=sub_question.question,
                answer="Insufficient information found to answer this question.",
                key_findings=[],
                sources=[],
                confidence="low",
                completeness="insufficient",
            )

        # Format findings for synthesis - INCLUDE source IDs for citations
        findings_text = "\n\n".join(
            [
                f"[{f.source_ids[0] if f.source_ids else 'unknown'}] Finding: {f.claim}\nEvidence: {f.evidence}\nConfidence: {f.confidence}"
                for f in findings
            ]
        )

        # Synthesize answer
        messages = [
            SystemMessage(content=ANSWER_SYNTHESIS_PROMPT),
            HumanMessage(
                content=f"Question: {sub_question.question}\n\n"
                f"Research Findings ({len(findings)} total) - USE THESE [source_id] FOR CITATIONS:\n{findings_text}\n\n"
                f"Write a COMPLETE, COMPREHENSIVE answer (500-1000 words) using ALL relevant findings above. "
                f"**CRITICAL: Include [source_id] citations for EVERY factual claim.** "
                f"Example: 'Player X averaged 30 points [src_abc123].' This is required."
            ),
        ]

        response = self.llm.invoke(messages)
        answer_text = response.content

        # Validate answer isn't truncated
        if len(answer_text) < 300 or answer_text.rstrip().endswith(('...', '—', '–')):
            # Answer seems cut off, retry with explicit instruction
            messages[-1] = HumanMessage(
                content=f"Question: {sub_question.question}\n\n"
                f"Research Findings ({len(findings)} total):\n{findings_text}\n\n"
                f"IMPORTANT: Your previous response was too short or incomplete. "
                f"Write a FULL answer of at least 500 words covering ALL the findings. Do not stop early."
            )
            response = self.llm.invoke(messages)
            answer_text = response.content

        # Assess overall confidence and completeness
        confidence = self._assess_confidence(findings, sources)
        completeness = self._assess_completeness(findings, sources)

        return QuestionAnswer(
            question_id=sub_question.question_id,
            question=sub_question.question,
            answer=answer_text,
            key_findings=findings,
            sources=sources,
            confidence=confidence,
            completeness=completeness,
        )

    def research_question(
        self, sub_question: SubQuestion, main_query: str
    ) -> QuestionAnswer:
        """
        Optimized research workflow: Search → Collect URLs → Extract ONCE → Synthesize.

        This is MUCH cheaper than extracting on every search:
        - Phase 1: Quick searches to find candidate URLs (basic search, no extract)
        - Phase 2: ONE extract call for the best 10 unique URLs
        - Phase 3: Deep synthesis from rich content

        Args:
            sub_question: The question to research
            main_query: Original user query for context

        Returns:
            Complete QuestionAnswer with findings and sources
        """
        # PHASE 1: Collect candidate URLs via cheap searches
        queries = self.generate_search_queries(sub_question, main_query)
        
        # Collect all results from 4 queries
        all_results = []
        for query in queries[:4]:  # 4 queries per question
            results = self.search_tavily(query)
            all_results.extend(results)
        
        if not all_results:
            return QuestionAnswer(
                question_id=sub_question.question_id,
                question=sub_question.question,
                answer="No search results found.",
                key_findings=[],
                sources=[],
                confidence="low",
                completeness="insufficient",
            )
        
        # Deduplicate by URL, keeping highest score
        url_to_result = {}
        for r in all_results:
            url = r.get("url")
            score = r.get("score", 0)
            if url:
                if url not in url_to_result or score > url_to_result[url].get("score", 0):
                    url_to_result[url] = r
        
        # Sort by score and take top 10
        sorted_results = sorted(
            url_to_result.values(),
            key=lambda x: x.get("score", 0),
            reverse=True
        )
        all_search_results = sorted_results[:10]
        
        # PHASE 2: Extract full content from TOP 10 URLs (ONE API call)
        top_urls = [r["url"] for r in all_search_results if r.get("url")]
        full_content = self.extract_full_content(top_urls)

        # Enrich results with full content
        for result in all_search_results:
            url = result.get("url")
            if url in full_content:
                result["full_content"] = full_content[url]

        # PHASE 3: Extract findings from enriched results
        all_findings, all_sources = self.extract_findings(all_search_results, sub_question)

        print(f"[Researcher] {sub_question.question_id}: {len(all_findings)} findings, {len(all_sources)} sources")

        # PHASE 4: Synthesize final answer
        answer = self.synthesize_answer(sub_question, all_findings, all_sources)
        return answer

    # Helper methods

    def _assess_confidence(
        self, findings: list[Finding], sources: list[SourceMetadata]
    ) -> str:
        """Assess overall confidence based on findings and sources."""
        if len(sources) >= 5 and len(findings) >= 4:
            return "high"
        elif len(sources) >= 3 and len(findings) >= 2:
            return "medium"
        else:
            return "low"

    def _assess_completeness(
        self, findings: list[Finding], sources: list[SourceMetadata]
    ) -> str:
        """Assess answer completeness."""
        # Adjusted thresholds - extract_findings targets 3-6 findings
        if len(findings) >= 3 and len(sources) >= 3:
            return "complete"
        elif len(findings) >= 2:
            return "partial"
        else:
            return "insufficient"

    def improve_research(
        self,
        sub_question: SubQuestion,
        previous_answer: str,
        improvement_suggestion: str,
        previous_sources: list[SourceMetadata] | None = None,
        suggested_searches: list[str] | None = None,
    ) -> QuestionAnswer:
        """
        Improve research using reflection's suggested searches directly.

        Simple flow:
        1. Use suggested_searches as queries (no LLM generation)
        2. Search and extract content
        3. Synthesize improved answer
        """
        previous_sources = previous_sources or []
        suggested_searches = suggested_searches or []

        # Use suggested_searches directly as queries
        queries = suggested_searches[:4] if suggested_searches else [improvement_suggestion]

        print(f"[Researcher] {sub_question.question_id}: re-searching with {len(queries)} queries")

        # Collect all results
        all_results = []
        for query in queries:
            results = self.search_tavily(query, max_results=5)
            all_results.extend(results)

        if not all_results:
            return self._make_answer(sub_question, previous_answer, [], [])
        
        # Deduplicate by URL, keeping highest score
        url_to_result = {}
        for r in all_results:
            url = r.get("url")
            score = r.get("score", 0)
            if url:
                if url not in url_to_result or score > url_to_result[url].get("score", 0):
                    url_to_result[url] = r
        
        # Sort by score and take top 10
        sorted_results = sorted(
            url_to_result.values(),
            key=lambda x: x.get("score", 0),
            reverse=True
        )
        top_results = sorted_results[:10]

        # Extract content from top URLs
        top_urls = [r["url"] for r in top_results if r.get("url")]
        full_content = self.extract_full_content(top_urls)
        for r in top_results:
            if r.get("url") in full_content:
                r["full_content"] = full_content[r["url"]]

        # Extract findings
        findings, sources = self.extract_findings(top_results, sub_question)
        print(f"[Researcher] {sub_question.question_id}: {len(findings)} new findings, {len(sources)} sources")

        if not findings:
            return self._make_answer(sub_question, previous_answer, [], previous_sources)

        # Synthesize improved answer
        answer_text = self._synthesize_improved(
            sub_question, previous_answer, findings, improvement_suggestion
        )

        # Merge sources
        all_sources = self._merge_sources(sources, previous_sources)

        return QuestionAnswer(
            question_id=sub_question.question_id,
            question=sub_question.question,
            answer=answer_text,
            confidence=self._assess_confidence(findings, all_sources),
            completeness=self._assess_completeness(findings, all_sources),
            sources=all_sources,
            key_findings=findings,
        )

    def _make_answer(self, sq: SubQuestion, answer: str, findings: list, sources: list) -> QuestionAnswer:
        """Create a QuestionAnswer with defaults."""
        return QuestionAnswer(
            question_id=sq.question_id,
            question=sq.question,
            answer=answer,
            confidence="medium",
            completeness="partial",
            sources=sources,
            key_findings=findings,
        )

    def _synthesize_improved(self, sq: SubQuestion, prev_answer: str, findings: list[Finding], gap: str) -> str:
        """Synthesize an improved answer."""
        prompt = f"""Improve this answer by addressing the gap.

QUESTION: {sq.question}
GAP TO ADDRESS: {gap}

PREVIOUS ANSWER:
{prev_answer[:2000]}

NEW FINDINGS:
{self._format_findings_for_synthesis(findings)}

Write a complete, improved answer that addresses the gap. Include [source_id] citations:"""

        response = self.llm.invoke([
            SystemMessage(content=RESEARCHER_SYSTEM_PROMPT.format(date_context=get_current_date_context())),
            HumanMessage(content=prompt),
        ])
        return response.content

    def _merge_sources(self, new: list[SourceMetadata], prev: list) -> list[SourceMetadata]:
        """Merge new and previous sources, avoiding duplicates."""
        all_sources = new.copy()
        seen = {s.url for s in all_sources}

        for src in prev:
            if isinstance(src, dict):
                url = src.get("url", "")
                if url and url not in seen:
                    seen.add(url)
                    all_sources.append(SourceMetadata(**src))
            elif src.url not in seen:
                seen.add(src.url)
                all_sources.append(src)

        return all_sources

    def _format_findings_for_synthesis(self, findings: list[Finding]) -> str:
        """Format findings for the synthesis prompt."""
        parts = []
        for f in findings[:15]:  # Limit to avoid token overflow
            source_ref = f.source_ids[0] if f.source_ids else "?"
            parts.append(f"- [{source_ref}] {f.claim}: {f.evidence[:200]}")
        return "\n".join(parts)

    def compress_research(self, answer: QuestionAnswer, sub_question: SubQuestion) -> str:
        """Compress research findings for compiler."""
        if not answer.sources:
            return f"## {sub_question.question}\n\nNo sources found.\n"

        try:
            context = self._build_compression_context(
                answer, sub_question, self.config.chars_per_source
            )
            response = self.llm.invoke([
                SystemMessage(content=COMPRESS_RESEARCH_PROMPT),
                HumanMessage(content=context),
            ])
            return f"# Research: {sub_question.question}\n\n{response.content}"
        except Exception as e:
            # Fallback: use original answer if compression fails (e.g., token limits)
            print(f"[Compress] Error compressing {sub_question.question_id}: {e}")
            return f"# Research: {sub_question.question}\n\n{answer.answer}"

    def _build_compression_context(
        self, answer: QuestionAnswer, sub_question: SubQuestion, chars_per_source: int
    ) -> str:
        """Build context for compression."""
        source_texts = []
        for source in answer.sources:
            content = source.full_content[:chars_per_source]
            source_texts.append(f"### [{source.id}] {source.title}\nURL: {source.url}\n\n{content}\n")

        return f"""## Research Question: {sub_question.question}

## Synthesized Answer:
{answer.answer}

## Source Materials:
{"".join(source_texts)}
"""



def researcher_node(state: ResearchState, config: RunnableConfig | None = None) -> dict:
    """
    LangGraph node: Research a single sub-question.

    Handles both:
    - Initial research (no previous_answer)
    - Improvement (has previous_answer + improvement_suggestion)

    Returns:
        Updates to question_answers and compressed_findings for this question.
    """
    # Get sub_question (may be dict from Send)
    sq = state.get("sub_question")
    if not sq:
        raise ValueError("researcher_node requires 'sub_question'")

    # Convert dict to SubQuestion if needed
    if isinstance(sq, dict):
        sq = SubQuestion(**sq)

    main_query = state.get("main_query", state.get("original_query", ""))

    # Initialize researcher
    agent_config = get_config(config or {})
    researcher = Researcher(config=agent_config)

    # Decide: initial research or improvement?
    prev_answer = state.get("previous_answer")
    prev_sources = state.get("previous_sources", [])
    suggestion = state.get("improvement_suggestion")

    # Get suggested_searches from reflection (if re-researching)
    suggested_searches = state.get("suggested_searches", [])

    if prev_answer and suggestion:
        # IMPROVEMENT: Re-research with suggested_searches
        answer = researcher.improve_research(
            sq, prev_answer, suggestion, prev_sources, suggested_searches
        )
    else:
        # INITIAL: Fresh research
        answer = researcher.research_question(sq, main_query)

    # Compress for report
    compressed = researcher.compress_research(answer, sq)

    return {
        "question_answers": {sq.question_id: answer},
        "compressed_findings": {sq.question_id: compressed},
    }

