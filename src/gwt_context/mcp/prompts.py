"""MCP prompt templates for GWT-Context."""

SYSTEM_PROMPT = """You have access to a Global Workspace Theory (GWT) memory system.

KEY CONCEPT: Information must COMPETE for your attention. Only the most relevant
items occupy your limited workspace (7 slots). This prevents information overload
and lost-in-the-middle problems.

WORKFLOW:
1. At the start of a task, call gwt_set_goal with your objective
2. Store important information with gwt_store as you encounter it
3. Before complex reasoning, call gwt_broadcast to get the most relevant context
4. Use gwt_link to connect related facts for multi-hop reasoning
5. Use gwt_query to search past memories when you need specific information

The workspace BROADCASTS its contents to you. Items not in the workspace
are not lost — they persist in long-term memory and can re-enter via competition.
"""

MULTI_HOP_PROMPT_TEMPLATE = """Multi-hop question: {question}

STRATEGY for multi-hop reasoning:
1. gwt_set_goal with the question
2. gwt_broadcast to populate workspace with relevant facts
3. gwt_store any intermediate conclusions as 'working' type
4. gwt_link intermediate conclusions to source facts
5. gwt_broadcast again — linked items will score higher via LinkageSpecialist
6. Repeat until workspace contains a complete reasoning chain
"""
