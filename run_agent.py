#!/usr/bin/env python3
"""
Simple script to run the research agent.

For full interactive experience, use LangGraph Studio: `langgraph dev`
"""

import sys
from dotenv import load_dotenv

from src import create_research_graph

load_dotenv()


def main():
    """Run research agent on a query."""
    if len(sys.argv) < 2:
        print("Usage: python run_agent.py '<your research question>'")
        print("Example: python run_agent.py 'What is the impact of AI on healthcare?'")
        sys.exit(1)

    query = " ".join(sys.argv[1:])
    print(f"🔍 Researching: {query}\n")

    try:
        graph = create_research_graph()
        result = graph.invoke({
            "original_query": query,
            "messages": [],
        })

        print("\n✅ Complete!\n")
        print(result.get("final_report", "No report generated"))

    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
