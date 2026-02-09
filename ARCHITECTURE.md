# Architecture Overview

This document provides a high-level overview of the deep research agent's architecture, file structure, and data flow.

---

## System Architecture

### High-Level Flow

```
User Query → Planner → Parallel Research → Aggregate → Reflection → [Loop if needed] → Compiler → Report
```

### Core Components

1. **Planner**: Decomposes user query into structured sub-questions
2. **Parallel Researcher**: Answers each sub-question concurrently
3. **Aggregator**: Merges results from parallel branches
4. **Reflection**: Analyzes quality and identifies improvements
5. **Compiler**: Generates final report with planned structure

---

## File Structure & Responsibilities

### Core Files

#### `src/graph.py` - Orchestration Layer
- Defines the LangGraph workflow with 5 nodes
- Implements routing logic between nodes
- Manages parallel execution with `Send()` API
- Controls iteration loop (max 2 re-research cycles)
- ~164 lines

**Key Functions:**
- `create_research_graph()`: Builds and compiles the LangGraph
- `route_after_planner()`: Fans out to parallel researchers
- `route_after_reflection()`: Decides whether to re-research or compile
- `aggregate_research()`: Merges parallel research results

---

#### `src/state.py` - Data Schema
- Defines all Pydantic models and TypedDict state
- Implements custom reducers for parallel state merging
- ~131 lines

**Key Models:**
- `ResearchState`: Complete state container (messages, plan, answers, findings)
- `ResearchPlan`: Flat list of sub-questions
- `SubQuestion`: Individual research question with strategy
- `QuestionAnswer`: Research result with findings and sources
- `AgentAnalysis`: Reflection output with assessment and suggestions
- `SourceMetadata`: Source with full content
- `Finding`: Structured claim with evidence and citations

**Custom Reducers:**
- `merge_question_answers()`: Merges answers from parallel researchers
- `merge_compressed_findings()`: Merges compressed summaries

---

#### `src/planner.py` - Query Decomposition
- Decomposes user queries into sub-questions
- Uses Research Question Taxonomy (7 types)
- Generates search strategies for each question
- ~120 lines

**Process:**
1. Parse user preferences (style, audience, focus areas)
2. Apply Research Question Taxonomy
3. Generate 8-10 sub-questions covering different aspects
4. Assign importance levels (critical, important, supporting)

**Taxonomy Categories:**
- Definitional (What is X?)
- Descriptive (How does X work?)
- Comparative (X vs Y?)
- Causal/Explanatory (Why does X happen?)
- Evaluative (How good is X?)
- Contextual (What influences X?)
- Forward-Looking (What's next for X?)

---

#### `src/researcher.py` - Web Search & Synthesis
- Executes web searches via Tavily API
- Extracts structured findings from sources
- Synthesizes comprehensive answers
- Cost-optimized with 3-phase pattern
- ~636 lines

**Key Methods:**
- `research_question()`: Initial research (3-phase pattern)
- `improve_research()`: Re-research using reflection's suggestions
- `generate_search_queries()`: Creates targeted search queries
- `search_tavily()`: Cheap basic search
- `extract_full_content()`: ONE expensive extract call per question
- `extract_findings()`: LLM extracts structured findings
- `synthesize_answer()`: Generates comprehensive answer with citations
- `compress_research()`: Summarizes findings for compiler

**3-Phase Cost Optimization:**
1. **Phase 1**: 4 cheap searches to collect candidate URLs
2. **Phase 2**: ONE extract call for top 10 URLs (expensive but efficient)
3. **Phase 3**: Deep synthesis with findings extraction

---

#### `src/reflection.py` - Quality Analysis
- Analyzes research quality
- Identifies weak answers
- Generates targeted improvement suggestions
- Tracks iteration count
- ~218 lines

**Process:**
1. Format all research for LLM analysis
2. LLM evaluates each answer against quality criteria
3. Identify weak answers (cut off, insufficient sources, gaps)
4. Generate `suggested_searches` for each weak answer
5. Decide: "needs_improvement", "adequate", or "strong"

**Output:**
- `overall_assessment`: Overall quality rating
- `weak_answers`: List of questions needing improvement
- `knowledge_gaps`: Missing information
- `suggested_questions`: Additional angles to explore
- `suggested_searches`: Specific queries for re-research

---

#### `src/compiler.py` - Report Generation
- Two-step report compilation process
- Plans optimal structure based on findings
- Generates sections with specific guidance
- Formats citations and references
- ~313 lines

**Two-Step Process:**
1. **Plan Report Structure**: LLM analyzes findings and decides optimal structure
2. **Generate Sections**: Create each section with non-overlapping content guidance

**Key Methods:**
- `compile_report()`: Main orchestration
- `_plan_report()`: LLM decides structure based on findings
- `_generate_section()`: Creates individual section
- `_format_citations()`: Numbered reference list

**Typical Output Structure (Dynamic):**
- Introduction (600-800 words)
- Subject Deep-Dives (600-800 words each)
- Analytical Framework (600-800 words)
- Contextual Factors (500-700 words)
- Multi-Faceted Conclusions (600-800 words)
- Final Synthesis (400-600 words)
- References (numbered list)

---

#### `src/prompts.py` - Methodology Prompts
- Centralized system prompts
- Methodology-driven frameworks
- ~378 lines

**Key Prompts:**
- `PLANNER_SYSTEM_PROMPT`: Research Question Taxonomy
- `RESEARCHER_SYSTEM_PROMPT`: Data Collection Framework (quant/qual)
- `REFLECTION_SYSTEM_PROMPT`: Quality Evaluation Framework
- `COMPILER_SYSTEM_PROMPT`: Report structure guidance
- `ANSWER_SYNTHESIS_PROMPT`: Citation requirements
- `COMPRESS_RESEARCH_PROMPT`: Compression instructions

**Methodology Frameworks:**
- Research Question Taxonomy (7 categories)
- Data Collection Framework (Quantitative vs Qualitative)
- Source Classification (Primary, Secondary, Institutional, Expert, Media)
- Quality Evaluation Framework (4-part checklist)

---

#### `src/config.py` - Runtime Configuration
- Defines `AgentConfig` Pydantic model
- All parameters configurable at runtime
- ~40 lines

**Configuration Parameters:**
- `model`: OpenAI model (default: gpt-4o)
- `temperature`: LLM temperature (default: 0.1)
- `max_search_results`: Results per query (default: 8)
- `max_iterations`: Max re-research cycles (default: 2)
- `min_sources_per_question`: Minimum sources (default: 3)
- `chars_per_source`: Content preserved (default: 15000)
- `target_report_words`: Final report target (default: 5500)

---

## Data Flow Patterns

### 1. Initial Research Phase

```
Planner
  ↓ (creates ResearchPlan with 10 sub-questions)
route_after_planner()
  ↓ (returns list of Send() objects)
Parallel Researchers (10 concurrent)
  ↓ (each returns question_answers + compressed_findings)
Aggregator (merge_question_answers reducer)
  ↓ (state now has all 10 answers)
Reflection
```

### 2. Iteration Phase (If Needed)

```
Reflection
  ↓ (identifies 4 weak answers)
  ↓ (generates suggested_searches)
route_after_reflection()
  ↓ (returns Send() objects with suggested_searches)
Parallel Re-Researchers (4 concurrent)
  ↓ (use suggested_searches, merge with previous_sources)
Aggregator
  ↓ (merge_question_answers updates 4 answers)
Reflection (check again)
```

### 3. Compilation Phase

```
Reflection (overall_assessment = "adequate")
  ↓
route_after_reflection() → "compiler"
  ↓
Compiler
  ↓ Step 1: Plan structure based on findings
  ↓ Step 2: Generate each section
  ↓ Step 3: Format citations
  ↓
Final Report (5000-6000 words)
```

---

## State Management

### State Schema

```
ResearchState {
  messages: list[BaseMessage]              # Chat history
  original_query: str                      # User's query
  report_preferences: ReportPreferences    # Parsed from query
  research_plan: ResearchPlan              # Flat list of sub-questions
  question_answers: dict[id, QuestionAnswer]  # Merged by reducer
  compressed_findings: dict[id, str]       # Merged by reducer
  current_iteration: int                   # Tracks re-research cycles
  agent_analysis: AgentAnalysis            # Reflection output
  next_step: "create_tasks" | "compile"   # Routing control
  final_report: str                        # Final output
}
```

### Custom Reducers

**Why needed?** Parallel execution with `Send()` creates multiple branches. Each branch updates state independently. Reducers merge these updates.

**Example:**
```
Initial: question_answers = {}
Branch 1 (Q1): question_answers = {Q1: answer1}
Branch 2 (Q2): question_answers = {Q2: answer2}
...
After merge: question_answers = {Q1: answer1, Q2: answer2, ..., Q10: answer10}
```

---

## Design Patterns

### 1. Cost Optimization Pattern

**Problem:** Tavily extract API is expensive
**Solution:** Batch cheap searches, then ONE extract call

```
Instead of:
  Query 1 → Search + Extract (expensive)
  Query 2 → Search + Extract (expensive)
  Query 3 → Search + Extract (expensive)
  Query 4 → Search + Extract (expensive)
  
Do:
  Query 1 → Search (cheap)
  Query 2 → Search (cheap)
  Query 3 → Search (cheap)
  Query 4 → Search (cheap)
  Collect top 10 unique URLs
  ONE Extract call for all 10 (expensive but only once)
```

**Savings:** 75% reduction on extract API calls

---

### 2. Compression Pattern

**Problem:** 10 questions × 5 sources × 15K chars = 750K chars to compiler
**Solution:** Each researcher compresses its own findings

```
Researcher (parallel) → compress_research() → compressed_findings
                     → full details → question_answers
                     
Compiler receives:
  - compressed_findings: 10 summaries (~8K words total)
  - sources: Available for citations
```

**Why this works:**
- Researcher has full context about its specific question
- Compression happens in parallel (no bottleneck)
- Compiler gets focused summaries, not raw data dumps

---

### 3. Iteration Control Pattern

**Problem:** Infinite reflection loops
**Solution:** Max iteration counter + merge strategy

```
current_iteration = 0

Reflection → "needs_improvement" AND weak_answers AND current_iteration < 2
  ↓ Yes
  current_iteration += 1
  Re-research weak answers (merge with previous)
  ↓
Reflection (again)

If current_iteration >= 2 OR "adequate":
  ↓ No more loops
  Proceed to compiler
```

**Guarantees:** Never more than 2 re-research cycles

---

### 4. Parallel Execution Pattern

**Problem:** Researching 10 questions sequentially is slow
**Solution:** LangGraph `Send()` API for fan-out

```
route_after_planner():
  return [
    Send("parallel_researcher", {sub_question: Q1, ...}),
    Send("parallel_researcher", {sub_question: Q2, ...}),
    ...
    Send("parallel_researcher", {sub_question: Q10, ...}),
  ]
  
All 10 execute concurrently
Aggregator waits for all to complete
State merged via custom reducers
```

---

## Key Architectural Decisions

### 1. Flat vs Nested Structure
- **Tried:** Nested themes containing sub-questions
- **Chose:** Flat list of sub-questions
- **Why:** Simpler, easier to evaluate, no added value from nesting

### 2. Compression Location
- **Tried:** Compress in compiler
- **Chose:** Compress in parallel researcher
- **Why:** Researcher has full context, parallelizes compression, no bottleneck

### 3. Iteration Mechanism
- **Tried:** Re-generate queries from scratch
- **Chose:** Reflection provides `suggested_searches` directly
- **Why:** Prevents repeating same searches, targeted improvements

### 4. State vs Filesystem
- **Tried:** Save intermediate results to files
- **Chose:** State-only (no file I/O)
- **Why:** Simpler, faster, better LangSmith Studio visibility

### 5. Human Review vs Autonomous
- **Tried:** Human-in-the-loop for plan and findings
- **Chose:** Fully autonomous with reflection
- **Why:** Faster iteration, no bottleneck, suitable for take-home demo

---

## Performance Characteristics

### Per Research Query (10 sub-questions, 4 re-researched)

**API Calls:**
- 56 Tavily searches (cheap: ~$0.06)
- 14 Tavily extracts (expensive: ~$0.07)
- ~42 LLM calls (GPT-4o: ~$0.50-$1.50)

**Timing:**
- Initial research (10 parallel): ~60-90 seconds
- Reflection: ~5-10 seconds
- Re-research (4 parallel): ~30-45 seconds
- Reflection (again): ~5-10 seconds
- Compilation: ~30-60 seconds
- **Total:** ~2-3 minutes per query

**Output:**
- 5000-6000 words
- 10-15 unique sources
- Inline citations throughout
- Structured with 7-10 sections

---

## Extension Points

### Easy to Modify

1. **Search API**: Change 2 methods in `researcher.py`
   - `search_tavily()` → `search_exa()`
   - `extract_full_content()` → `exa_get_contents()`

2. **Prompts**: All in `prompts.py`, easy to customize
   - Modify Research Question Taxonomy
   - Adjust report structure guidance
   - Change quality evaluation criteria

3. **Configuration**: All parameters in `config.py`
   - Add new fields to `AgentConfig`
   - Access via `get_config(config)`

4. **New Nodes**: Modular graph in `graph.py`
   - Add node function
   - Add to workflow
   - Update routing logic

5. **State Fields**: Add to `state.py`
   - Define new field in `ResearchState`
   - Add custom reducer if needed for parallel merging

---

## Guardrails & Constraints

### Hard Limits
- Max 2 re-research iterations (prevents infinite loops)
- Max 10 URLs extracted per question (cost control)
- Max 4 search queries per question (quality/cost balance)

### Soft Limits (Configurable)
- Target 5500 words for final report
- Minimum 3 sources per question
- 15,000 chars preserved per source

### Quality Thresholds
- 5+ findings + 5+ sources = "high" confidence
- 3+ findings + 3+ sources = "complete"
- < 3 findings or < 3 sources = "needs_improvement"

---

## Testing Strategy

### What's Tested
- Basic imports and graph creation
- End-to-end manual testing
- A/B comparison with Gemini Deep Research
- Cost optimization verification (API call counting)

### What's Not Tested (Future Work)
- Unit tests for reflection logic
- Unit tests for state reducers
- Integration tests for iteration loops
- Evaluation metrics on diverse query types
- Edge case handling (empty results, API failures)

---

## Production Readiness

### ✅ Production-Quality Elements
- Type hints throughout
- Specific exception handling (not generic)
- Custom reducers for parallel state
- Guaranteed iteration termination
- Cost optimization documented
- Modular, single-responsibility architecture
- Professional logging with `[Module]` prefixes

### ⚠️ Not Production-Ready (Future Work)
- Limited test coverage
- No monitoring/observability
- No retry logic for transient failures
- No caching for repeated queries
- No streaming (waits for full completion)
- No dynamic depth adjustment (simple queries get full treatment)

---

## Summary

This architecture demonstrates a **production-quality deep research agent** built in 5-6 hours with:
- **Systematic methodology** (Research Question Taxonomy, not ad-hoc)
- **Cost efficiency** (75% reduction on expensive API calls)
- **Robust iteration control** (guaranteed termination, no infinite loops)
- **Clean engineering** (modular, typed, specific exceptions, custom reducers)
- **Professional output** (5000-6000 word reports with proper citations)

The design emphasizes **simplicity** (5 nodes, flat structure), **efficiency** (parallel execution, smart batching), and **quality** (methodology-driven prompts, iterative improvement).

