# Only backfill when the retained successful checks cover the recorded count.
BACKFILL_FIRST_PRICE = """
UPDATE watch_items
SET first_price = (
    SELECT current_price
    FROM price_checks
    WHERE watch_item_id = watch_items.id AND status = 'ok' AND current_price IS NOT NULL
    ORDER BY checked_at, id
    LIMIT 1
)
WHERE first_price IS NULL AND successful_check_count <= (
    SELECT COUNT(*)
    FROM price_checks
    WHERE watch_item_id = watch_items.id AND status = 'ok' AND current_price IS NOT NULL
)
"""
