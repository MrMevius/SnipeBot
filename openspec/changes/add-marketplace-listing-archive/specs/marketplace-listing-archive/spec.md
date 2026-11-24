## ADDED Requirements

### Requirement: Found listings are archived locally
The system SHALL archive every listing recorded by a saved search, including listings recorded silently by the first check, with its details and all photos.

#### Scenario: Archive a new listing
- **WHEN** a search check records a listing that is not archived yet
- **THEN** an archive item is queued
- **AND** the worker stores title, price, description, attributes, seller details, statistics and all photos of the listing page

#### Scenario: Existing listings are backfilled
- **WHEN** search listings exist without an archive item
- **THEN** the worker creates archive items for them and archives them

### Requirement: Archive keeps history
The system SHALL re-fetch archived listings on price or title changes and weekly while online, and SHALL store a new version only when the content changed.

#### Scenario: Unchanged listing
- **WHEN** a re-fetch returns the same content
- **THEN** no new version is stored and known photos are not downloaded again

#### Scenario: Changed listing
- **WHEN** the description or photos changed
- **THEN** a new version is stored
- **AND** photos no longer in the listing are kept and marked as removed

#### Scenario: Removed listing
- **WHEN** the listing page returns HTTP 410 or 404
- **THEN** the archive item is marked gone and all archived data is kept

### Requirement: Archive fetching is throttled
The system SHALL fetch listing pages one at a time with a delay and a time budget per worker tick, and SHALL pause archiving with increasing backoff when Marktplaats blocks requests.

#### Scenario: Blocked
- **WHEN** a listing page or photo request returns HTTP 403 or 429
- **THEN** the current tick stops and no archive requests are made until the backoff has passed

### Requirement: Archived listings can be browsed
The system SHALL provide an archive overview across searches and a listing page per archived listing.

#### Scenario: Listing page
- **WHEN** a client requests `GET /archive/{id}`
- **THEN** the response includes the sanitized description, attribute groups, seller, statistics, photos, price history and versions with their changes

#### Scenario: Archive survives search deletion
- **WHEN** a saved search is deleted
- **THEN** its archived listings remain available in the archive

#### Scenario: Delete from archive
- **WHEN** a client deletes an archived listing
- **THEN** its rows and photo files are removed
