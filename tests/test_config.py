from shared.config import (
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    TOP_K,
    MIN_PRIMARY,
    GENERAL_THIN_PRIMARY,
    LLM_TIMEOUT,
    AGENT_TIMEOUT,
    JOB_TIMEOUT,
    URL_FETCH_TIMEOUT,
    URL_FETCH_CONCURRENCY,
    MAX_FILES,
    MAX_FILE_MB,
    MAX_URLS,
    MAX_URL_BYTES,
    JOB_RETENTION_MAX,
    JOB_RETENTION_TTL_SECONDS,
)


def test_job_timeout_covers_four_sequential_agents():
    assert JOB_TIMEOUT >= 4 * AGENT_TIMEOUT
    assert JOB_TIMEOUT == 300
    assert AGENT_TIMEOUT == 60
    assert MIN_PRIMARY == 3
    assert GENERAL_THIN_PRIMARY == 2
    assert GENERAL_THIN_PRIMARY != MIN_PRIMARY
    assert TOP_K == 5
    assert MAX_FILES == 40
    assert MAX_FILE_MB == 25
    assert MAX_URLS == 20
    assert MAX_URL_BYTES == 5 * 1024 * 1024
    assert JOB_RETENTION_MAX == 50
    assert JOB_RETENTION_TTL_SECONDS == 30 * 60
