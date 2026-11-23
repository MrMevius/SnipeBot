## ADDED Requirements

### Requirement: Users can save a Marktplaats search from a results URL
The system SHALL let a user create a saved search from a marktplaats.nl search results URL with a name, optional exclude keywords and a seller filter (`all`, `private`, `business`).

#### Scenario: Preview before saving
- **WHEN** a client submits `POST /searches/preview` with a valid Marktplaats results URL
- **THEN** the response lists the understood filters as readable lines, any ignored filters as warnings, the total result count and up to five sample listings

#### Scenario: Reject non-search URLs
- **WHEN** the URL is not on marktplaats.nl or is not a results page (`/l/…` or `/q/…`)
- **THEN** the backend responds with a 422 validation error

#### Scenario: Seller filter
- **WHEN** a search is saved with seller type `private` or `business`
- **THEN** the stored search request filters on the matching Marktplaats advertiser value

### Requirement: First check records listings silently
The system SHALL record the listings returned by the first successful check of a search, and by the first check after its keywords or seller filter change, without sending alerts.

#### Scenario: Baseline
- **WHEN** a new search is checked for the first time
- **THEN** all matching listings are stored as baseline listings
- **AND** no Telegram message is sent

### Requirement: New matching listings trigger one Telegram alert
The system SHALL send exactly one Telegram alert for each genuinely new listing that matches the search and does not contain an exclude keyword.

#### Scenario: New listing
- **WHEN** a later check returns a listing id above the highest id known for the search
- **THEN** one alert is sent with photo, title, price, car details when available, place and distance, seller type, search name and link

#### Scenario: Bumped older listing
- **WHEN** a later check returns an unseen listing with an id below the known maximum and the previous check did not cover the complete result set
- **THEN** the listing is stored without an alert

#### Scenario: Excluded keyword
- **WHEN** a listing title or description contains an exclude keyword (case-insensitive)
- **THEN** the listing is neither stored nor alerted

### Requirement: Price drops of known listings trigger an alert
The system SHALL alert once per price drop of a known listing and keep its price history.

#### Scenario: Price drop
- **WHEN** a known listing's price is lower than its last recorded price
- **THEN** one alert is sent showing old price, new price and difference
- **AND** repeated checks at the same price send no further alert

### Requirement: Checks are scheduled, bounded and fail safely
The system SHALL check active searches about every 10 minutes with jitter, cap alerts per check and back off on errors without sending alerts.

#### Scenario: Marktplaats error
- **WHEN** Marktplaats returns an error or unparsable data
- **THEN** the search records the error kind and message, schedules a retry with backoff and sends no alerts

#### Scenario: Alert flood
- **WHEN** more than 10 alerts are due for one search in one check
- **THEN** 10 alerts are sent and one summary message covers the rest

### Requirement: Users can manage searches and view listings
The system SHALL provide UI and API to list, pause/resume, check now, edit (name, exclude keywords, seller) and delete searches, and to list recorded listings with new/gone state and price history.

#### Scenario: Listing overview
- **WHEN** a user opens a saved search
- **THEN** recorded listings are shown with photo, price (and earlier price), car details, location, seller and first-seen time, with "new" for listings found after the baseline within 48 hours
