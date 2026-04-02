## Purpose

Define watchlist management behavior for URL-based product tracking setup.

## Requirements

### Requirement: Users can save watched items from product URL input
The system SHALL allow creating a watched item by submitting a product URL with optional custom label and optional target price.

#### Scenario: Create watched item with required and optional fields
- **WHEN** a client submits `POST /watchlist` with a valid URL and optional fields
- **THEN** the backend persists a watched item containing `url`, `custom_label`, `target_price`, `site_key`, and `active`
- **AND** `active` defaults to `true` for new items

### Requirement: Backend validates and normalizes product URLs
The system SHALL validate submitted URLs and normalize them where reasonable for storage and deduplication.

#### Scenario: Reject malformed URL
- **WHEN** a client submits an invalid or malformed URL
- **THEN** the backend responds with a client validation error

#### Scenario: Normalize valid URL
- **WHEN** a client submits a valid URL with removable tracking fragments/parameters
- **THEN** the backend stores a normalized URL representation used for deduplication

### Requirement: Duplicate submissions use upsert behavior by normalized URL
The system SHALL update the existing watched item instead of creating a duplicate when the same normalized URL is submitted.

#### Scenario: Upsert by URL
- **WHEN** a client submits `POST /watchlist` for a URL already in watchlist (same normalized URL for owner)
- **THEN** the existing watched item is updated with new optional values
- **AND** no duplicate watched item row is created

### Requirement: Users can deactivate watched items
The system SHALL allow marking a watched item as inactive without deleting it.

#### Scenario: Deactivate watched item
- **WHEN** a client requests deactivation for an existing watched item
- **THEN** the watched item `active` flag is set to `false`
- **AND** the item remains available in watchlist listing results

### Requirement: System detects and stores adapter-style site key
The system SHALL classify submitted URLs into site keys aligned with adapter names.

#### Scenario: Detect supported site key
- **WHEN** a submitted URL host matches a supported site
- **THEN** the stored `site_key` is one of `hema`, `amazon_nl`, or `aliexpress`

#### Scenario: Unknown site fallback
- **WHEN** a submitted URL host does not match known sites
- **THEN** the stored `site_key` is `unknown`

### Requirement: Watchlist overview returns plain data for UI
The system SHALL provide a list endpoint returning watched items including overview fields for frontend rendering.

#### Scenario: List watched items
- **WHEN** a client requests `GET /watchlist`
- **THEN** the response contains saved watched items with `url`, `custom_label`, `target_price`, `site_key`, `active`
- **AND** includes `current_known_price`, `last_check_time`, and `status`

### Requirement: Frontend provides compact add form and overview page
The system SHALL provide a simple frontend workflow with a compact add form and plain watchlist overview.

#### Scenario: User adds and sees watched item in overview
- **WHEN** a user submits the add form with a valid product URL
- **THEN** the item appears in the watchlist overview with expected fields
- **AND** the UI remains plain and functional without design-heavy styling
