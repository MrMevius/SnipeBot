## Context

The repository already contains a FastAPI backend, SQLite wiring, and a minimal React shell. There is no watchlist CRUD yet. The next increment should stay small but establish durable contracts and seams for future adapter-based scraping and future multi-user evolution.

## Goals / Non-goals

**Goals:**
- Persist watched items with fields: `url`, `custom_label`, `target_price`, `site_key`, and `active`.
- Normalize product URLs in backend where reasonable.
- Map `site_key` values to adapter names (`hema`, `amazon_nl`, `aliexpress`).
- Provide compact add form and plain watchlist overview in frontend.
- Show `current_known_price`, `last_check_time`, and `status` in watchlist overview.
- Keep data model future-safe for multi-user by including an owner seam.

**Non-goals:**
- Live scraping during form submission beyond lightweight safe metadata extraction.
- Notifications.
- Scheduled checks.
- Authentication.
- UI polish beyond basic functional layout.

## Decisions

1. **Upsert by normalized URL for single-user owner.**
   - Use unique key `(owner_id, normalized_url)` and owner default `local`.
   - Re-submitting same normalized URL updates the existing item.

2. **Site detection is adapter-key classification, not scraping.**
   - Determine `site_key` from URL hostname only.
   - Return fallback `unknown` for unsupported hosts.

3. **Store overview fields now as nullable values.**
   - `current_known_price`, `last_check_time`, and `status` exist to support list display.
   - This change does not implement fetch/scheduling that updates these values.

4. **Active flag is persisted and defaults to true in v1.**
   - No toggle endpoint/UI in this change.

## Risks / Trade-offs

- **Normalization mistakes may dedupe too aggressively or not enough.**
  - Mitigate by applying conservative normalization (lowercase host, strip fragments/default ports, remove common tracking params).
- **Status semantics could drift before scheduler exists.**
  - Keep default simple (`pending`) and document that real updates come in later changes.
