## MODIFIED Requirements

### Requirement: Watchlist overview returns latest check snapshot fields
The system SHALL provide a list endpoint returning watched items including snapshot fields used by scheduled checking.

#### Scenario: List watched items with snapshot fields
- **WHEN** a client requests `GET /watchlist`
- **THEN** each item includes `last_checked_at`, `last_status`, and `current_price`
- **AND** fields remain nullable when no successful checks exist

### Requirement: Worker updates watched item status from scheduled checks
The system SHALL update watched item snapshot fields when checks are attempted.

#### Scenario: Successful scheduled check updates snapshot
- **WHEN** a due active watched item is checked successfully
- **THEN** `last_checked_at` is updated
- **AND** `last_status` is set to `ok`
- **AND** `current_price` reflects parsed price value

#### Scenario: Failed scheduled check keeps last known price
- **WHEN** a due active watched item check fails to fetch or parse
- **THEN** `last_checked_at` is updated
- **AND** `last_status` reflects failure (`fetch_error` or `parse_error`)
- **AND** existing `current_price` is not cleared
