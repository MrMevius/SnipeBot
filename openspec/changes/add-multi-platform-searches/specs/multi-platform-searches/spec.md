## ADDED Requirements

### Requirement: Searches use SnipeBot's own filters
The system SHALL define a saved search by make, model and optional ranges for year, price, mileage, minimum range and battery capacity, plus seller, exclude words and alert price ceiling.

#### Scenario: Choose a car
- **WHEN** the owner chooses a make
- **THEN** the models of that make are listed with the platforms that offer each model

### Requirement: A search covers several platforms
The system SHALL check each selected platform separately with its own baseline, schedule and error state.

#### Scenario: Add a platform
- **WHEN** a platform is added to an existing search
- **THEN** its current listings are recorded silently and the other platforms keep their state

#### Scenario: One platform fails
- **WHEN** a platform returns an error or blocks requests
- **THEN** the other platforms of the search are still checked

### Requirement: Unsupported filters are applied by SnipeBot
The system SHALL check filters a platform cannot apply against the listing data, and SHALL keep listings that do not state the value, marked as unknown.

#### Scenario: Battery capacity unknown
- **WHEN** a listing on a platform without a battery filter does not state its battery capacity
- **THEN** the listing is recorded and shown with "battery capacity unknown"
- **AND** an alert for it names the missing value

### Requirement: Existing searches keep working
The system SHALL turn searches created from a Marktplaats URL into a Marktplaats source with their query and check state.

#### Scenario: Switch to filters
- **WHEN** such a search is given filters that produce the same Marktplaats query
- **THEN** no new baseline is recorded
