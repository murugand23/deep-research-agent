"""
Deep Research Agent Graph.

SIMPLIFIED FLOW:
1. planner → parallel_researcher (fan out) → aggregate → reflection
2. reflection: if weak answers AND iteration < 2 → fan out to researcher with suggested_searches
3. reflection: if done → compiler → END
"""

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from .compiler import compiler_node
from .planner import planner_node
from .reflection import reflection_node
from .researcher import researcher_node
from .state import ResearchPlan, ResearchState

MAX_ITERATIONS = 2


# =============================================================================
# Helpers
# =============================================================================

def _get_plan(state: ResearchState) -> ResearchPlan | None:
    plan = state.get("research_plan")
    if not plan:
        return None
    return ResearchPlan(**plan) if isinstance(plan, dict) else plan


def _get_weak_answers(state: ResearchState) -> list[dict]:
    analysis = state.get("agent_analysis")
    if not analysis:
        return []

    weak = analysis.get("weak_answers", []) if isinstance(analysis, dict) else (analysis.weak_answers or [])

    return [
        wa if isinstance(wa, dict) else {"question_id": wa.question_id, "issue": wa.issue, "suggestion": wa.suggestion}
        for wa in weak
    ]


def _get_suggested_searches(state: ResearchState) -> list[str]:
    analysis = state.get("agent_analysis")
    if not analysis:
        return []
    return analysis.get("suggested_searches", []) if isinstance(analysis, dict) else (analysis.suggested_searches or [])


def _get_answer_data(state: ResearchState, q_id: str) -> tuple[str, list]:
    answers = state.get("question_answers", {})
    answer = answers.get(q_id)
    if not answer:
        return "", []
    return (answer.get("answer", ""), answer.get("sources", [])) if isinstance(answer, dict) else (answer.answer, getattr(answer, "sources", []))


# =============================================================================
# Routing
# =============================================================================

def route_after_planner(state: ResearchState) -> list[Send]:
    """Fan out to researchers for each sub-question."""
    plan = _get_plan(state)
    if not plan:
        return [Send("compiler", state)]

    main_query = state.get("original_query", "")
    return [
        Send("parallel_researcher", {"sub_question": sq, "main_query": main_query})
        for sq in plan.sub_questions
    ]


def aggregate_research(state: ResearchState) -> dict:
    """Aggregate after parallel research."""
    qa = state.get("question_answers", {})
    print(f"[Aggregate] Collected {len(qa)} answers")
    return {}


def route_after_reflection(state: ResearchState) -> list[Send]:
    """
    After reflection:
    - If weak answers AND iteration < MAX: fan out to researchers with suggested_searches
    - Otherwise: go to compiler
    """
    iteration = state.get("current_iteration", 0)
    weak_answers = _get_weak_answers(state)
    suggested_searches = _get_suggested_searches(state)
    needs_improvement = state.get("next_step") == "re_research"

    # If done or max iterations reached → compiler
    if not needs_improvement or iteration >= MAX_ITERATIONS or not weak_answers:
        print(f"[Router] Complete (iteration={iteration}, weak={len(weak_answers)}) -> compiler")
        return [Send("compiler", state)]

    # Need improvement → fan out to researchers with suggested_searches
    plan = _get_plan(state)
    if not plan:
        return [Send("compiler", state)]

    sq_map = {sq.question_id: sq for sq in plan.sub_questions}

    sends = []
    for wa in weak_answers:
        q_id = wa["question_id"]
        sq = sq_map.get(q_id)
        if not sq:
            continue

        prev_text, prev_sources = _get_answer_data(state, q_id)

        print(f"[Router] Re-research {q_id} with suggested_searches: {suggested_searches[:2]}")

        sends.append(Send("parallel_researcher", {
            "sub_question": sq,
            "previous_answer": prev_text,
            "previous_sources": prev_sources,
            "improvement_suggestion": wa["suggestion"],
            "suggested_searches": suggested_searches,  # THE KEY: pass suggested searches
        }))

    return sends if sends else [Send("compiler", state)]


# =============================================================================
# Graph
# =============================================================================

def create_research_graph() -> StateGraph:
    """
    Simple flow:
        planner → [researchers] → aggregate → reflection
                                                  ↓
                            [researchers with suggested_searches] (if weak, max 2x)
                                                  ↓
                                              compiler → END
    """
    workflow = StateGraph(ResearchState)

    # Nodes
    workflow.add_node("planner", planner_node)
    workflow.add_node("parallel_researcher", researcher_node)
    workflow.add_node("aggregate", aggregate_research)
    workflow.add_node("reflection", reflection_node)
    workflow.add_node("compiler", compiler_node)

    # Edges
    workflow.add_edge(START, "planner")
    workflow.add_conditional_edges("planner", route_after_planner, ["parallel_researcher", "compiler"])
    workflow.add_edge("parallel_researcher", "aggregate")
    workflow.add_edge("aggregate", "reflection")
    workflow.add_conditional_edges("reflection", route_after_reflection, ["parallel_researcher", "compiler"])
    workflow.add_edge("compiler", END)

    return workflow.compile()


graph = create_research_graph()
