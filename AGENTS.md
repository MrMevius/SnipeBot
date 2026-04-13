# Repository Agent Rules (Local Fallback)

Deze file borgt lokaal gedrag voor deze repository.

## Plan Intake Protocol (MC-first)

Bij elk verzoek om te plannen (plan/planning/execution plan) start de assistant met een verplichte intake in multiple-choice (MC) vorm.

### 1) Trigger
- Start **altijd** met MC-intake bij elk planverzoek.

### 2) Minimale verplichte kernset (single-choice)
Stel minimaal deze vragen:
1. Doel: wat moet het plan opleveren?
2. Scope: wat valt expliciet in scope en out of scope?
3. Constraints: tijd, techniek, policies, afhankelijkheden.
4. Prioriteit/volgorde: must-have vs nice-to-have.
5. Acceptatiecriteria: wanneer is het klaar?
6. Verificatie: welke checks/tests/commands bewijzen succes?

### 3) Antwoordvorm
- Standaard: **single-choice per vraag**.
- Gebruik korte, duidelijke opties.
- Sta eigen antwoord toe indien nodig.

### 4) Ontbrekende informatie
- Als na de kernset nog cruciale informatie ontbreekt, doe **precies één** extra gerichte MC-ronde.

### 5) Verplichte output na intake
- Lever altijd een scherpe plan-brief met minimaal:
  - Doel
  - Scope
  - Constraints
  - Aanpak (genummerde stappen)
  - Mapping naar acceptatiecriteria
  - Verificatie (exacte checks/commands)

## Voorbeeldinteracties

### Voorbeeld A — basisflow
1. User: "Maak een plan om feature X te bouwen."
2. Assistant: start MC-intake met de 6 kernvragen (single-choice).
3. User: beantwoordt alle vragen.
4. Assistant: levert plan-brief met Doel, Scope, Constraints, Aanpak, Mapping naar acceptatiecriteria, Verificatie.

### Voorbeeld B — ontbrekende informatie
1. User: "Geef een implementatieplan voor Y."
2. Assistant: stelt de 6 kernvragen.
3. User: laat cruciale info open (bijv. verificatie of scope-grens).
4. Assistant: doet precies één extra gerichte MC-ronde voor die ontbrekende info.
5. Assistant: levert daarna de volledige plan-brief.
