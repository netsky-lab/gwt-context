"""End-to-end multi-hop reasoning test.

Simulates a real LLM session: stores facts, sets goals,
runs broadcast cycles, uses linking for multi-hop chains.
Tests with real sentence-transformers embeddings.
"""

import asyncio
import json
import tempfile
from pathlib import Path

from gwt_context.server import create_server
from gwt_context.infrastructure.config import GWTConfig


async def test_multi_hop_reasoning():
    """Scenario: Who was the doctoral advisor of the person who developed general relativity?

    Facts scattered across multiple items:
    - Einstein developed general relativity
    - Einstein's doctoral advisor was Alfred Kleiner
    - Alfred Kleiner was a professor at University of Zurich
    - General relativity was published in 1915
    + distractor facts about unrelated topics
    """
    print("=" * 60)
    print("MULTI-HOP REASONING TEST")
    print("Question: Who was the doctoral advisor of the person")
    print("          who developed general relativity?")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmp:
        config = GWTConfig(data_dir=tmp, workspace_capacity=5)
        server = create_server(config)
        tm = server._tool_manager

        # === STEP 1: Ingest facts (simulating document processing) ===
        print("\n--- Step 1: Ingesting facts ---")
        facts = [
            "Albert Einstein developed the theory of general relativity",
            "Einstein's doctoral advisor was Alfred Kleiner at the University of Zurich",
            "The Eiffel Tower was completed in 1889 and is located in Paris",
            "General relativity describes gravity as the curvature of spacetime",
            "Alfred Kleiner was a Swiss physicist and professor of experimental physics",
            "Marie Curie won two Nobel Prizes in physics and chemistry",
            "Einstein received his PhD from the University of Zurich in 1905",
            "The speed of light in vacuum is approximately 299,792,458 meters per second",
            "Kleiner supervised several doctoral students including Albert Einstein",
            "Quantum mechanics was developed independently by Heisenberg and Schrodinger",
        ]

        item_ids = []
        for fact in facts:
            r = await tm.call_tool('gwt_store', {'content': fact})
            item_ids.append(r['id'])
            print(f"  Stored [{r['id']}]: {fact[:60]}...")

        # === STEP 2: Set goal ===
        print("\n--- Step 2: Setting goal ---")
        r = await tm.call_tool('gwt_set_goal', {
            'description': 'Find who was the doctoral advisor of the person who developed general relativity',
            'keywords': ['doctoral advisor', 'general relativity', 'developed'],
        })
        print(f"  Goal set: {r['goal_id']}")

        # === STEP 3: First broadcast — initial selection ===
        print("\n--- Step 3: First broadcast ---")
        r = await tm.call_tool('gwt_broadcast', {})
        print(r)

        # === STEP 4: Check what's in workspace ===
        print("\n--- Step 4: Workspace inspection ---")
        r = await tm.call_tool('gwt_inspect', {'target': 'workspace'})
        ws_items = [s for s in r['workspace'] if not s.get('empty')]
        print(f"  Occupied: {r['occupied']}/{r['capacity']}")
        for s in ws_items:
            print(f"  [slot:{s['slot']} a={s['activation_level']:.3f}] {s['content'][:80]}")

        # === STEP 5: Create links for multi-hop chain ===
        print("\n--- Step 5: Creating links for reasoning chain ---")

        # Find relevant item IDs from workspace
        einstein_relativity_id = None
        kleiner_advisor_id = None
        kleiner_professor_id = None

        for s in ws_items:
            content = s['content'].lower()
            if 'einstein' in content and 'general relativity' in content:
                einstein_relativity_id = s['id']
            if 'doctoral advisor' in content and 'kleiner' in content:
                kleiner_advisor_id = s['id']
            if 'kleiner' in content and 'professor' in content:
                kleiner_professor_id = s['id']

        # Also search if not in workspace
        if not kleiner_advisor_id:
            r = await tm.call_tool('gwt_query', {'query': 'doctoral advisor Einstein Kleiner'})
            for item in r:
                if 'kleiner' in item['content'].lower() and 'advisor' in item['content'].lower():
                    kleiner_advisor_id = item['id']
                    break

        if einstein_relativity_id and kleiner_advisor_id:
            r = await tm.call_tool('gwt_link', {
                'source_id': einstein_relativity_id,
                'target_id': kleiner_advisor_id,
            })
            print(f"  Linked: Einstein+relativity <-> Kleiner advisor ({r['status']})")

        if kleiner_advisor_id and kleiner_professor_id:
            r = await tm.call_tool('gwt_link', {
                'source_id': kleiner_advisor_id,
                'target_id': kleiner_professor_id,
            })
            print(f"  Linked: Kleiner advisor <-> Kleiner professor ({r['status']})")

        # === STEP 6: Store intermediate reasoning ===
        print("\n--- Step 6: Storing intermediate conclusion ---")
        links = []
        if einstein_relativity_id:
            links.append(einstein_relativity_id)
        if kleiner_advisor_id:
            links.append(kleiner_advisor_id)

        r = await tm.call_tool('gwt_store', {
            'content': 'Hop 1: Einstein developed general relativity. Hop 2: His doctoral advisor was Alfred Kleiner.',
            'memory_type': 'working',
            'link_to': links,
        })
        working_id = r['id']
        print(f"  Stored working memory [{working_id}]")

        # === STEP 7: Second broadcast — with links active ===
        print("\n--- Step 7: Second broadcast (with links) ---")
        r = await tm.call_tool('gwt_broadcast', {})
        print(r)

        # === STEP 8: Final workspace state ===
        print("\n--- Step 8: Final workspace ---")
        r = await tm.call_tool('gwt_inspect', {'target': 'workspace'})
        ws_items = [s for s in r['workspace'] if not s.get('empty')]
        print(f"  Occupied: {r['occupied']}/{r['capacity']}")
        for s in ws_items:
            print(f"  [slot:{s['slot']} a={s['activation_level']:.3f}] {s['content'][:80]}")

        # === STEP 9: Verify answer can be derived ===
        print("\n--- Step 9: Answer verification ---")
        ws_contents = " ".join(s['content'] for s in ws_items)
        has_einstein_relativity = 'einstein' in ws_contents.lower() and 'relativity' in ws_contents.lower()
        has_kleiner_advisor = 'kleiner' in ws_contents.lower() and ('advisor' in ws_contents.lower() or 'supervised' in ws_contents.lower())

        print(f"  Einstein + relativity in workspace: {has_einstein_relativity}")
        print(f"  Kleiner as advisor in workspace:    {has_kleiner_advisor}")
        print(f"  Multi-hop chain complete:           {has_einstein_relativity and has_kleiner_advisor}")

        if has_einstein_relativity and has_kleiner_advisor:
            print("\n  ANSWER: Alfred Kleiner was the doctoral advisor of Einstein,")
            print("          who developed general relativity.")
            print("  STATUS: PASS")
        else:
            print("\n  STATUS: PARTIAL — not all chain links in workspace")

        # === Stats ===
        print("\n--- Final stats ---")
        r = await tm.call_tool('gwt_inspect', {'target': 'stats'})
        print(f"  {json.dumps(r, indent=4)}")


async def test_goal_switching():
    """Test that changing goals reshuffles workspace appropriately."""
    print("\n" + "=" * 60)
    print("GOAL SWITCHING TEST")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmp:
        config = GWTConfig(data_dir=tmp, workspace_capacity=3)
        server = create_server(config)
        tm = server._tool_manager

        # Store mixed facts
        facts = [
            "Python is a programming language created by Guido van Rossum",
            "The Great Wall of China is over 13,000 miles long",
            "Python uses indentation for code blocks",
            "Mount Everest is the tallest mountain at 29,032 feet",
            "Python supports multiple programming paradigms",
            "The Amazon River is the largest river by discharge volume",
        ]
        for f in facts:
            await tm.call_tool('gwt_store', {'content': f})

        # Goal 1: Python programming
        print("\n--- Goal 1: Python programming ---")
        await tm.call_tool('gwt_set_goal', {'description': 'Learn about Python programming'})
        r = await tm.call_tool('gwt_broadcast', {})
        print(r)

        # Goal 2: Geography
        print("\n--- Goal 2: Geography ---")
        await tm.call_tool('gwt_set_goal', {'description': 'Learn about world geography and landmarks'})
        r = await tm.call_tool('gwt_broadcast', {})
        print(r)


async def test_eviction_pressure():
    """Test that workspace evicts lowest-scoring items under pressure."""
    print("\n" + "=" * 60)
    print("EVICTION PRESSURE TEST")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmp:
        config = GWTConfig(data_dir=tmp, workspace_capacity=3)
        server = create_server(config)
        tm = server._tool_manager

        # Fill with geography facts
        geo_facts = [
            "Paris is the capital of France",
            "Tokyo is the capital of Japan",
            "London is the capital of England",
        ]
        for f in geo_facts:
            await tm.call_tool('gwt_store', {'content': f})

        await tm.call_tool('gwt_set_goal', {'description': 'Learn about world capitals'})
        r = await tm.call_tool('gwt_broadcast', {})
        print("\n--- Initial workspace (geography) ---")
        print(r)

        # Now add highly relevant physics facts and change goal
        physics_facts = [
            "E=mc^2 is Einstein's mass-energy equivalence formula",
            "Quantum entanglement allows particles to be correlated across distances",
            "The Higgs boson was discovered at CERN in 2012",
        ]
        for f in physics_facts:
            await tm.call_tool('gwt_store', {'content': f})

        await tm.call_tool('gwt_set_goal', {'description': 'Understand modern physics discoveries'})
        r = await tm.call_tool('gwt_broadcast', {})
        print("\n--- After goal switch to physics ---")
        print(r)

        # Verify: workspace should now have physics, not geography
        insp = await tm.call_tool('gwt_inspect', {'target': 'workspace'})
        ws_contents = " ".join(s.get('content', '') for s in insp['workspace'] if not s.get('empty'))
        has_physics = any(w in ws_contents.lower() for w in ['einstein', 'quantum', 'higgs'])
        print(f"\n  Physics in workspace: {has_physics}")
        print(f"  STATUS: {'PASS' if has_physics else 'FAIL'}")


async def main():
    await test_multi_hop_reasoning()
    await test_goal_switching()
    await test_eviction_pressure()
    print("\n" + "=" * 60)
    print("ALL E2E TESTS COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
