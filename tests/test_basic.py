"""Basic tests to verify the agent components work."""

import pytest


def test_imports():
    """Test that all modules can be imported."""
    from src import create_research_graph, ResearchState, AgentConfig
    from src.state import ResearchPlan, SubQuestion
    from src.planner import Planner
    from src.researcher import Researcher
    from src.reflection import ReflectionAnalyzer
    from src.compiler import ReportCompiler

    assert create_research_graph is not None
    assert ResearchState is not None
    assert AgentConfig is not None


def test_graph_creation():
    """Test that graph can be created without errors."""
    from src import create_research_graph

    app = create_research_graph()

    assert app is not None
    assert hasattr(app, "invoke")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
