# DESIGN.md

## Background

### Testing Existing Solutions
- I started with testing both Gemini Deep Research Agent and OpenAI Deep Research Mode to understand the requirements and output quality.

### Test prompts
1. Who's the best player in the NBA? (please see example_report.txt)
2. Beyond popular practices like gratitude or meditation, what's a scientifically validated yet underutilized approach for profoundly transforming one's sense of fulfillment, authenticity, and daily motivation?

---

## Initial Architecture

### Request Flow (v1)
1. User enters their initial query
2. Planner agent (planner.py) decomposes query into a set of themes
3. Human in the loop approval/feedback step for planner output before research step
4. Independently research each theme in parallel using external search APIs (Tavily)
5. Additional human in the loop approval/feedback step for research findings
6. Using a multi-step compilation process, synthesize the findings and write them into a structured report using a two-step compilation process

### Early Decisions
-  I added detailed prompts with the current date programatically injected at runtime (prompts.py) and initially started with gpt4o-mini to understand how the agent behaves at a baseline

- I stored research findings and extracted web content in LangGraph state (see ResearchState in state.py), approach for transparency in LangSmith Studio (I also debated storing in a filesystem.)

- I removed the human in the loop review steps for planning and reviewing findings. Originally, these review steps were meant to accept user feedback before research and compilation respectively, but I eventually removed them. Instead, user preferences are now incorporated as part of the initial request, causing the model to return a `ReportPreferences` type as part of the planning step.

- I switched to a sub-question based research approach (Generate max. 10 sub-questions from the user's question to conduct research) from specific themes. Having 10 sub-questions while generating 3-4 search queries per sub-question is a tunable way to control the breadth and depth of research, whereas specific themes felt very high-level.  

- Compiler (report-generation) agent uses a two-pass approach (to manage context for report generation) to:
  1. Synthesize the findings from researcher agents, generate a report outline
  2. Use the report outline to generate the report using another LLM call (one-shot)

---

## What Worked Well

### Source-Grounded Citations
- **The "Compiler with Tools" Failure:** I initially tried to give the compiler agent tools to search for context on the fly. However, the model context window exploded. I had to remove the tools for the writer to get more context. Though this approach didn't work, this constraint forced me to implement the strict `[source_id]` tracking system. Since the writer couldn't "look it up," the researcher *had* to provide explicit, cited evidence for everything. The result is a system that is far less prone to hallucination because the compiler is a synthesizer of verified facts.

### Search Quality
- Adding the current date context (programatically injected) and detailed prompts for each node improved web search quality

- User preferences are now incorporated as part of the initial request, causing the model to return a `ReportPreferences` type as part of the planning step. Therefore the raw user input can be analyzed to detect audience type, style, focus_areas, and report constraints (word count) and that will be used during report generation.


### Query Generation
- Generating search queries for each sub-question helped get diverse sources rather than using the main query repeatedly

---

## What Didn't Work

### Context Window Issues
### Report Generation Strategy
- Iteration on report generation strategy
- Drawbacks of my first approach:
  1. First pass - the compiler took every sub-question's raw answer from the `question_answers` dict (often thousands of words each) along with their full source content, and put all of that into a giant context. This hit size limits almost immediately on longer topics. The compressed findings were injected into the system prompt for the report generation agent.
  2. Second pass - The report generator (compiler) tried to write the whole report in one go using the report plan, with various sub-question/answer pairs in its prompt. This often led to context overflows or just a poor synthesis because the prompt was too crowded. Additionally one-shot report generation for ALL sections was not comprehensive for depth. 
- Fix: moved the compression process to the researcher nodes and added an aggregator node to collect results before passing to compiler. Additionally I changed the generation logic to use the report plan as context (from the first pass) and generate ONE section at a time dynamically.This made sure as sections were generated the agent had context on research/the questions it was trying to answer without spending tokens focusing on other sections at the same time.

### Human Review Steps
- Human in the loop step after generating sub-questions added too much friction
- Fix: made it fully autonomous, reflection agent reviews the ResearchState and decides whether the research is adequate enough (for the compiler to start planning/writing the report), or needs improvement and suggests follow up questions for the researcher. 
### Search Result Selection
- Initial approach used Tavily extract from first 10 URLs from 4 queries evenly - this meant none of the search results were evaluated based on their quality
- Fix: added score-based re-ranking across all query results using Tavily's score field, which improved research quality

---

## Known Limitations

### Report Structure
- The report structure (intro → conclusion) is functional but could be more dynamic based on query type. Since the report is being generated one section at a time, each individual section can have its own introduction → conclusion structure. Even though the content is not repetitive, the repetitive format could be fixed by generating the report headings/sub-headings for each section in the report plan and enforcing that the structure is flexible and unique before passing it into the report generation step. 

### Search Depth vs. Breadth
- **Problem:** Current implementation is configured at max. 10 sub-questions, 4 queries per sub-question, 2 iterations of reflection, 5 search results per Tavily request (can be changed in config.py). Only one Tavily extract request is made for every 10 URLs. 
- **How to fix:** Add dynamic depth based on the complexity of a query
  - Simple queries: fewer sub-questions, more depth per question, more search queries per question
  - Complex queries: more sub-questions, balanced depth
  - Could use an LLM call in planner to classify query complexity

### Token Limits
- **Problem:** Large QuestionAnswer objects in the research state can still approach context limits
- **How to fix:** Implement better research compression and streaming compilation - currently we are truncating content returned from a web search using chars_per_source from the config

---

## Future Improvements

### Cost vs. Quality Tradeoffs
- Search depth vs cost - currently doing 4 queries × 5 results = 20 basic searches per sub-question
- Could make this adaptive based on query type (factual vs. opinion-based) or dynamically pick different breadth vs depth configurations (less expensive vs more expensive) based on user intent. 
- To tune breadth -> increase the number of generated sub-questions, number of search queries per sub-question
- To tune depth -> decrease the number of sub-questions, increase the number of searches per sub-question and returned search results from Tavily. Increase the number of URLs to extract from. 

### Report Generation
- Could add more sophisticated formatting
- Better handling of tables and structured data
- Dynamic section ordering based on query intent

### Context Management
- Handling large context - implement tool-calling for getting research context and more robust chunking and compression strategies to handle model context window limits.
---

## Configuration System

Made the agent configurable via `config.py` and runtime configuration:
- `model` - LLM model selection (default: gpt-4o)
- `temperature` - LLM temperature (default: 0.1 for researcher)
- `max_search_results` - results per Tavily query (default: 5)
- `max_questions` - max sub-questions from planner (default: 10)
- `max_iterations` - max reflection iterations (default: 2)
- `chars_per_source` - compression limit per source (default: 12000)

This allows tuning the depth/cost tradeoff without code changes by passing a `configurable` dict at runtime.

