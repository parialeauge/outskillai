from scripts.lancedb_prefilter_check import run_prefilter_check
from scripts.lancedb_prefilter_check import run_where_check


def test_where_returns_expected_rows():
    hits = run_where_check()

    assert len(hits) == 3
    assert all(hit["category"] == "pm" for hit in hits)


def test_prefilter_returns_all_matching_rows_even_when_k_exceeds_matches():
    hits = run_prefilter_check()

    assert len(hits) == 3
    assert all(hit["category"] == "pm" for hit in hits)
