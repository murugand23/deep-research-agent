# Deep Research Agent 🕵️‍♂️

**Author:** Murugan Dhanushkodi (<murugan.n.dhanushkodi@gmail.com>)

A comprehensive, autonomous research agent built with **LangGraph** that performs deep web research, synthesizes findings, and generates structured reports.

![Agent Architecture](https://github.com/langchain-ai/langgraph/raw/main/docs/static/img/langgraph_logo.png) *Architecture diagram available in DESIGN.md*

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

The agent follows a **Plan-and-Execute** architecture with a feedback loop:

1. **Planner:** Decomposes the user's query into a structured research plan (max 10 sub-questions).
2. **Parallel Researcher:**
   - Fans out to research each sub-question independently.
   - Performs multiple Tavily searches (4 queries × 5 results).
   - Re-ranks results by score and extracts full content from top 10 URLs.
   - Synthesizes an answer with citations and compresses it.
3. **Aggregator:** Collects results from all parallel branches.
4. **Reflection:** Analyzes the quality of research (completeness, sources). If gaps are found, it triggers a **re-research loop** (max 2 iterations).
5. **Compiler:**
   - **Phase 1:** Plans the report structure based on findings.
   - **Phase 2:** Generates the final report section-by-section.

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

**Configuration in Studio:**
You can adjust the following parameters in the "Configuration" tab before running:
- `max_search_results`: Number of results per query (Default: 5)
- `max_questions`: Max sub-questions to generate (Default: 10)
- `max_iterations`: Max re-research loops (Default: 2)
- `model`: OpenAI model to use (Default: gpt-4o)

### Option 2: CLI / Python

You can run the agent programmatically:

```python
from src.graph import create_research_graph

graph = create_research_graph()
result = graph.invoke({
    "messages": [HumanMessage(content="Who is the best NBA player in 2026?")]
})

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
