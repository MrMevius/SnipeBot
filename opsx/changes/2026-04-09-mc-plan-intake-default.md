# Title
MC-first intake als standaard bij planverzoeken (globaal)

## Context
De gebruiker wil dat OpenCode/OpenSpec bij elk planverzoek eerst alle noodzakelijke verduidelijkingsvragen stelt in multiple-choice vorm. Doel is om vragen scherper te maken vóór planning. Deze voorkeur moet globaal gelden op deze machine.

Scope-update tijdens uitvoering: vanwege sandbox-permissies is directe wijziging van het globale bestand (`/home/mevius/.config/opencode/AGENTS.md`) in deze sessie niet mogelijk. Daarom implementeren we een repository-fallback in `AGENTS.md` op projectroot, zodat dit gedrag binnen deze repo direct afdwingbaar is.

## Goals / Non-goals
### Goals
1. Leg het gewenste plan-intakegedrag vast in actieve agent-instructies voor deze repo (fallback via project `AGENTS.md`).
2. Definieer een minimale verplichte kernset intakevragen.
3. Definieer gedrag bij ontbrekende informatie: precies één extra gerichte MC-ronde.
4. Definieer output na intake: altijd een scherpe plan-brief met vaste onderdelen.
5. Voeg korte voorbeeldinteractie(s) toe om toepassing en edge-case gedrag consistent te maken.

### Non-goals
1. Geen wijzigingen aan repositorycode (backend/frontend).
2. Geen wijziging aan OpenSpec skillbestanden.
3. Geen UI-aanpassingen; alleen instructiegedrag.

## Proposed approach
1. Voeg een nieuwe sectie toe aan projectroot `AGENTS.md` met een expliciet protocol voor planintake.
2. Maak de regels concreet en uitvoerbaar met duidelijke trigger, volgorde, antwoordvorm en fallback.
3. Voeg een compacte sectie met voorbeeldinteractie toe (normale flow + één extra ronde bij ontbrekende info).
4. Gebruik formulering die conflict met bestaande regels minimaliseert (plan-first blijft intact).

## Implementation steps (ordered)
1. Maak projectroot `AGENTS.md` aan (bestond nog niet).
2. Voeg sectie `Plan Intake Protocol (MC-first)` toe met:
   - trigger: bij elk planverzoek,
   - minimale kernvragen,
   - single-choice standaard,
   - één extra gerichte MC-ronde indien nodig,
   - verplichte plan-brief outputstructuur.
3. Voeg sectie `Voorbeeldinteracties` toe met:
   - basisflow: MC-kernset -> plan-brief,
   - onvolledige input: precies één extra gerichte MC-ronde -> plan-brief.
4. Verifieer dat de tekst aanwezig en eenduidig is.
5. Update deze spec met status, wijzigingen en verificatie-evidence.

## Acceptance criteria (measurable)
1. Projectroot `AGENTS.md` bevat expliciet een sectie `Plan Intake Protocol (MC-first)`.
2. De sectie vereist MC-intake bij elk planverzoek.
3. De sectie beschrijft een minimale verplichte kernset vragen.
4. De sectie beschrijft dat antwoorden standaard single-choice zijn.
5. De sectie beschrijft precies één aanvullende gerichte MC-ronde bij ontbrekende info.
6. De sectie beschrijft dat output altijd een scherpe plan-brief bevat met ten minste: doel, scope, constraints, aanpak, acceptatiecriteria en verificatie.
7. `AGENTS.md` bevat een sectie met voorbeeldinteracties die zowel basisflow als de extra MC-ronde toont.

## Testing plan (canonical commands or approach)
1. Lees projectroot `AGENTS.md` en controleer dat alle acceptance criteria letterlijk terug te vinden zijn.
2. Handmatige gedragscheck in vervolgdialogen: bij een planverzoek start assistant met MC-vragen.

## Risk + rollback plan
### Risks
1. Te strikte intake kan wrijving geven bij kleine planvragen.
2. Mogelijke overlap/tegenstrijdigheid met bestaande globale regels.

### Mitigations
1. Houd kernset minimaal en praktisch.
2. Plaats protocol als aanvullende, heldere sectie met duidelijke prioriteit voor planverzoeken.

### Rollback
1. Verwijder de toegevoegde sectie uit projectroot `AGENTS.md`.
2. Herstel eventueel vorige versie via versiebeheer/back-up.

## Notes / links
- Doelbestand: `/home/mevius/snipebot/AGENTS.md`

## Current status
Completed

## What changed
- Nieuwe change spec aangemaakt voor globale MC-first planintake.
- Scope bijgesteld: implementatie gebeurt als repo-fallback in `AGENTS.md` op projectroot.
- Nieuw bestand toegevoegd: `AGENTS.md` op projectroot met sectie `Plan Intake Protocol (MC-first)` inclusief:
  - verplichte MC-start bij elk planverzoek,
  - minimale kernset van 6 vragen,
  - single-choice als standaard antwoordvorm,
  - precies één extra gerichte MC-ronde bij ontbrekende info,
  - verplichte plan-brief outputstructuur.
- `AGENTS.md` uitgebreid met sectie `Voorbeeldinteracties` met:
  - basisflow (MC-kernset -> plan-brief),
  - ontbrekende-info flow (één extra gerichte MC-ronde -> plan-brief).

## How to verify
1. Open `/home/mevius/snipebot/AGENTS.md`.
2. Controleer:
   - MC-intake bij elk planverzoek,
   - minimale verplichte kernset vragen,
   - single-choice als standaard,
   - precies één extra gerichte MC-ronde,
   - verplichte plan-brief met: doel, scope, constraints, aanpak, acceptatiecriteria, verificatie,
   - sectie `Voorbeeldinteracties` met basisflow en ontbrekende-info flow.
3. Start een nieuwe planaanvraag en bevestig dat de assistant eerst MC-vragen stelt.

## Verification evidence
- Specbestand aangemaakt: `opsx/changes/2026-04-09-mc-plan-intake-default.md`.
- Externe file access check gefaald (historisch):
  - poging: read `/home/mevius/.config/opencode/AGENTS.md`
  - resultaat: policy blokkeert `external_directory` buiten toegestane paden.
- Verificatie van lokaal fallback-bestand:
  - `read /home/mevius/snipebot/AGENTS.md`
  - resultaat: sectie `Plan Intake Protocol (MC-first)` en `Voorbeeldinteracties` met alle vereiste regels aanwezig.
- Testen: niet van toepassing (alleen instructie-/documentatiewijziging, geen repo-codepad gewijzigd).
