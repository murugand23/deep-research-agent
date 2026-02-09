# Deep Research Agent 🕵️‍♂️

**Author:** Murugan Dhanushkodi (<murugan.n.dhanushkodi@gmail.com>)

A comprehensive, autonomous research agent built with **LangGraph** that performs deep web research, synthesizes findings, and generates structured reports.

Screenshot 2026-02-09 at 9.50.39 AM.png
---

## 🚀 Features

- **Autonomous Research:** Decomposes complex queries into sub-questions and researches them in parallel.
- **Deep & Broad:** Generates multiple search queries per sub-question to ensure diverse sources.
- **Self-Correcting:** Includes a **Reflection** step that critiques research quality and triggers targeted re-research loops.
- **Source-Grounded:** All claims are cited inline `[source_id]` with a reference list.
- **Optimized for Quality & Cost:**
  - **Score-based Re-ranking:** Uses Tavily's relevance scores to pick the best 10 URLs across all queries.
  - **Compression:** Compresses individual answers to manage context window limits effectively.
- **Configurable:** Tunable depth, breadth, and iteration parameters via LangGraph Studio or code.

---

## 🛠️ Architecture

### Request Flow

1. **START → Planner** (`planner.py`)
   - User submits query
   - Planner decomposes into max. 10 sub-questions
   - Outputs ResearchPlan with sub-questions prioritized by importance

2. **Planner → Parallel Researcher** (`researcher.py`)
   - LangGraph fans out to research each sub-question in parallel using Send()
   - Each researcher:
     - Generates 4 search queries per sub-question
     - Performs 4 Tavily basic searches (5 results each = 20 total)
     - Re-ranks all 20 results by Tavily's score field
     - Extracts full content from top 10 URLs (single expensive API call)
     - Synthesizes answer with inline citations
     - Compresses answer for report compilation

3. **Parallel Researcher → Aggregator** (`graph.py`)
   - Synchronization point - waits for all parallel research to complete
   - Custom state reducers merge question_answers and compressed_findings from all branches

4. **Aggregator → Reflection** (`reflection.py`)
   - Analyzes research quality across all sub-questions
   - Identifies weak answers (incomplete, missing sources, cut off)
   - Outputs suggested_searches for improvement
   - Decision: needs_improvement vs. compile

5. **Reflection → (Re-research OR Compile)**
   - If needs_improvement AND current_iteration < 2:
     - Returns to Parallel Researcher with suggested_searches
     - Researcher uses suggested_searches directly (no LLM query generation)
     - Merges new findings with previous sources
   - Else: proceeds to Compiler

6. **Compiler → END** (`compiler.py`)
   - Two-step process:
     - Step 1: Plan report structure based on compressed_findings
     - Step 2: Generate report section-by-section with context from previous sections
   - Returns final markdown report with inline citations

### Key Implementation Details

- **State Management:** Uses LangGraph TypedDict with custom reducers for merging parallel results
- **Search Optimization:** Score-based re-ranking ensures all 4 queries contribute to top 10 URLs (not just first query)
- **Compression:** Each answer compressed at researcher level to avoid context window issues in compiler
- **Reflection Loop:** Max 2 iterations prevents infinite loops while allowing one improvement pass
- **Citation System:** Inline [source_id] citations tracked throughout pipeline from extraction to final report

---

## 📦 Setup

### Prerequisites
- Python 3.10+
- [Tavily API Key](https://tavily.com/)
- [OpenAI API Key](https://platform.openai.com/)

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/deep-research-agent.git
   cd deep-research-agent
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables:**
   Create a `.env` file in the root directory:
   ```bash
   TAVILY_API_KEY=tvly-...
   OPENAI_API_KEY=sk-...
   ```

---

## 🏃‍♂️ Usage

### Option 1: LangGraph Studio (Recommended)

1. Make sure you have LangGraph Studio installed.
2. Open the project folder in LangGraph Studio.
3. Select the `deep_research_agent` graph.
4. Enter your query in the input field and run!

### Option 2: CLI / Python

You can run the agent programmatically:

```python
from src.graph import create_research_graph

graph = create_research_graph()
result = graph.invoke({
    "messages": [HumanMessage(content="Who is the best NBA player in 2026?")]
}, {"configurable": {"model": "gpt-4o-mini"}})  # <-- Change model here

print(result["final_report"])
```

Or use the provided runner script (if available):
```bash
python run_agent.py "Your research query here"
```

---

## ⚙️ Configuration

The agent is fully configurable. You can change defaults in `src/config.py` or override them at runtime via `configurable` dict.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_search_results` | 5 | Number of results retrieved per Tavily search query. |
| `max_questions` | 10 | Maximum number of sub-questions the planner generates. |
| `max_iterations` | 2 | Maximum number of reflection/re-research loops. |
| `chars_per_source` | 12,000 | Character limit per source during compression. |
| `temperature` | 0.1 | LLM temperature for research tasks. |

---

## 📂 Project Structure

```
├── src/
│   ├── graph.py        # Main LangGraph workflow definition
│   ├── state.py        # State schema and TypedDicts
│   ├── planner.py      # Query decomposition logic
│   ├── researcher.py   # Search, extraction, synthesis, compression
│   ├── reflection.py   # Quality critique and iteration control
│   ├── compiler.py     # Report planning and generation
│   ├── prompts.py      # All LLM prompts
│   └── config.py       # Configuration schema
├── DESIGN.md           # Detailed engineering process and decisions
├── langgraph.json      # LangGraph Studio configuration
├── requirements.txt    # Python dependencies
└── README.md           # This file
```

---

## 🧠 Design Process

For a detailed breakdown of the engineering decisions, trade-offs, and iterations, please see [DESIGN.md](DESIGN.md).

---

**Built for the LangChain Deep Research Agent Take-home Assignment.**
