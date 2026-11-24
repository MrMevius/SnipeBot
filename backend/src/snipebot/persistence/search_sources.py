# Searches created from a pasted Marktplaats URL become one Marktplaats source
# that keeps their query and check state (baseline, id watermark, schedule).
COPY_LEGACY_SEARCH_SOURCES = """
INSERT INTO marketplace_search_sources (
    search_id, marketplace, query_json, post_filters_json, baseline_done, id_watermark,
    last_total_count, last_fetched_count, last_complete, last_checked_at, next_check_at,
    last_status, last_error_message, consecutive_failure_count, check_count, created_at
)
SELECT
    s.id, s.marketplace, s.query_json, '[]', s.baseline_done, s.id_watermark,
    s.last_total_count, s.last_fetched_count,
    COALESCE(s.last_total_count <= s.last_fetched_count, FALSE),
    s.last_checked_at, s.next_check_at, s.last_status, s.last_error_message,
    s.consecutive_failure_count, s.check_count, s.created_at
FROM marketplace_searches s
WHERE s.filters_json IS NULL
  AND NOT EXISTS (SELECT 1 FROM marketplace_search_sources x WHERE x.search_id = s.id)
"""
