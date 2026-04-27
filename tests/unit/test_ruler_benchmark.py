"""Tests for RULER-style benchmark generation."""

from tests.benchmarks.ruler_multi_hop import generate_tasks


def test_advisor_question_hop_count_matches_expected_chain_length() -> None:
    task = generate_tasks(n_hops_list=[2], distractor_counts=[1], tasks_per_config=1)[0]

    chain = {}
    for chunk in task.metadata["chain_facts"]:
        source, rest = chunk.split("'s doctoral advisor was ", 1)
        target = rest.split(" at ", 1)[0]
        chain[source] = target

    current = task.metadata["chain_facts"][0].split("'s doctoral advisor was ", 1)[0]
    for _ in range(task.question.count("doctoral advisor")):
        current = chain[current]

    assert task.question.count("doctoral advisor") == task.metadata["n_hops"]
    assert current == task.expected_answer
