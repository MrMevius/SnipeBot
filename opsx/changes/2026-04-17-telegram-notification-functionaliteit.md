# Title
Implement Telegram notificatie functionaliteit (MVP end-to-end)

## Context
Het project bevat al basisonderdelen voor alertregels en een Telegram-notifier, maar er is nog afronding nodig om de flow betrouwbaar end-to-end te maken voor runtime gebruik:
- events moeten consequent leiden tot Telegram-dispatch,
- configuratiegedrag moet voorspelbaar zijn (runtime toggles vs env-secrets),
- en verificatie moet aantonen dat berichten echt aankomen.

Aanvulling op verzoek: Telegram provider settings (`bot token`, `chat id`) moeten ook via de bestaande Settings UI instelbaar zijn.

## Goals / Non-goals
### Goals
1. Werkende Telegram-notificaties voor alert-events (`price_drop`, `target_reached`) in de worker-flow.
2. Runtime toggles uit `/settings` laten doorwerken voor notificatie-activatie.
3. Telegram provider settings (`bot token`, `chat id`) via Settings UI beheersbaar maken en direct laten doorwerken.
4. Lege UI-waarden laten terugvallen op env-defaults.
5. Duidelijke en testbare delivery-uitkomst in `alert_events`.

### Non-goals
1. Nieuwe notificatiekanalen (email/push/webhooks).
2. Per-user notificatiebeleid/multi-user routing.
3. Geavanceerd secret-management (vault-integratie, encryptie-at-rest schemawijzigingen).
4. Grote UI-uitbreidingen buiten bestaande settings schermflow.

## Proposed approach
1. Voeg een effectieve runtime settings-resolutie toe in de worker check-flow waarbij DB-toggles (`notifications_enabled`, `telegram_enabled`) de env-defaults kunnen overriden.
2. Breid settings API/domain uit met `telegram_bot_token` en `telegram_chat_id` die in `app_settings` opgeslagen kunnen worden.
3. Voorkom onnodige failed alert-events wanneer Telegram functioneel uitstaat (disabled/unconfigured), maar blijf echte providerfouten als `failed` registreren.
4. Gebruik runtime-resolutie met fallback: DB-waarde (indien niet leeg) anders env-default.
5. Breid tests uit voor settings load/save en runtime notifier gedrag.

## Implementation steps (ordered)
1. Nieuwe change spec aanmaken en activeren.
2. `backend/src/snipebot/domain/settings.py` + `backend/src/snipebot/api/settings.py` uitbreiden voor Telegram credentials in settings payload.
3. `backend/src/snipebot/domain/price_checks.py` uitbreiden met runtime-resolutie vanuit `app_settings` voor toggles + Telegram credentials met env fallback.
4. `backend/src/snipebot/notifications/factory.py` uitbreiden met optionele runtime overrides voor Telegram credentials.
5. Frontend settings-model en UI uitbreiden met Telegram bot token/chat ID velden.
6. Tests toevoegen/aanpassen in backend en frontend settings flows.
7. Verificatie draaien en spec updaten met bewijs.

## Acceptance criteria
1. Bij een geldige alert-trigger en ingeschakelde Telegram-notificaties wordt een Telegram-send uitgevoerd en een `alert_events` record met `delivery_status=sent` opgeslagen.
2. Als `notifications_enabled=false` of `telegram_enabled=false` via `/settings`, worden geen Telegram-sends uitgevoerd.
3. Als Telegram notifier disabled/unconfigured is, worden geen onnodige `failed` alert-events aangemaakt met `notifications_disabled`.
4. Bij echte Telegram providerfouten blijft een `failed` alert-event met foutreden opgeslagen.
5. Settings UI kan `telegram_bot_token` en `telegram_chat_id` ophalen en bewaren via `/settings`.
6. Runtime notifier gebruikt DB-credentials wanneer ingevuld; bij lege DB-waarden valt hij terug op env-defaults.

## Testing plan
Backend gericht:
```bash
pytest backend/tests/test_telegram_notifier.py -q
pytest backend/tests/test_alert_rules.py -q
pytest backend/tests/test_price_check_worker.py -q
pytest backend/tests/test_watchlist.py -q -k settings
```

Backend volledig:
```bash
pytest backend/tests -q
```

Frontend gericht:
```bash
cd frontend
npm run test -- App.test.tsx
```

Syntax sanity:
```bash
python3 -m compileall backend/src backend/tests
```

Handmatige smoke:
1. Zet `SNIPEBOT_NOTIFICATIONS_ENABLED=true`, `SNIPEBOT_TELEGRAM_ENABLED=true`, `SNIPEBOT_TELEGRAM_BOT_TOKEN`, `SNIPEBOT_TELEGRAM_CHAT_ID`.
2. Trigger check met alert-conditie.
3. Verifieer bericht in Telegram + `GET /watchlist/{id}/alerts`.

## Risk + rollback plan
### Risks
1. Onbedoelde gedragswijziging doordat worker nu DB-toggles respecteert.
2. Onvolledige suppressie van disabled notifier-resultaten.

### Mitigations
1. Gerichte unit/integratietests op toggle-combinaties.
2. Beperkte wijziging: alleen notificatiepad en geen schemawijzigingen.

### Rollback
1. Revert commit met wijzigingen in notificatiepad/tests.
2. Zet notificaties uit via env (`SNIPEBOT_NOTIFICATIONS_ENABLED=false`).

## Notes / links
- Relevante modules:
  - `backend/src/snipebot/domain/price_checks.py`
  - `backend/src/snipebot/notifications/factory.py`
  - `backend/src/snipebot/notifications/telegram.py`
  - `backend/src/snipebot/domain/settings.py`

## Current status
Completed (frontend test-executie in deze omgeving beperkt door ontbrekende Node/npm)

## What changed
- `backend/src/snipebot/domain/price_checks.py`
  - Runtime-resolutie toegevoegd voor notificatietoggles uit `app_settings` (`notifications_enabled`, `telegram_enabled`) met env-default fallback.
  - Worker gebruikt deze effectieve toggles voor notifier-opbouw en alert-dispatch gating.
  - Alerts worden niet meer als `failed` gepersisteerd wanneer notifier `notifications_disabled` retourneert (disabled/unconfigured pad).
- `backend/src/snipebot/notifications/factory.py`
  - `build_notifier(...)` ondersteunt optionele override flags voor `notifications_enabled` en `telegram_enabled`, zodat runtime toggles gecontroleerd toegepast kunnen worden zonder secrets in DB.
- `backend/tests/test_price_check_worker.py`
  - Bestaande notifier monkeypatches aangepast voor nieuwe factory-signature.
  - Nieuwe test: DB settings kunnen Telegram-dispatch uitschakelen ondanks env defaults.
  - Nieuwe test: `notifications_disabled` response resulteert niet in ruis-`failed` events.
  - Nieuwe test: echte providerfout (`Forbidden`) blijft als `failed` alert-event gepersisteerd.
  - Testisolatie verbeterd: `_reset_tables()` ruimt nu ook `app_settings` op om state-leakage tussen tests te voorkomen.
- UI-configuratie uitgebreid voor Telegram credentials:
  - `backend/src/snipebot/domain/settings.py`: `BackendSettings` en update-flow uitgebreid met `telegram_bot_token` + `telegram_chat_id`.
  - `backend/src/snipebot/api/settings.py`: response/request uitgebreid met `telegram_bot_token` + `telegram_chat_id`.
  - `backend/src/snipebot/domain/price_checks.py`: runtime settings-resolutie uitgebreid naar toggles + credentials met fallback op env-defaults wanneer DB-waarde leeg is.
  - `backend/src/snipebot/notifications/factory.py`: notifier factory accepteert nu optionele runtime overrides voor token/chat-id.
  - `backend/tests/test_watchlist.py`: settings endpoint test uitgebreid met Telegram credential velden.
  - `backend/tests/test_price_check_worker.py`: nieuwe test toegevoegd die aantoont dat DB credentials env credentials overriden voor runtime notifierconfiguratie.
  - `frontend/src/api/client.ts`: settings types/payload uitgebreid met Telegram credential velden.
  - `frontend/src/App.tsx`: Settings UI uitgebreid met invoervelden voor Telegram bot token en chat ID; save/load flow bijgewerkt.
  - `frontend/src/App.test.tsx`: settings test uitgebreid met Telegram velden en PATCH body-asserties.
- Telegram test-knop toegevoegd in Settings:
  - `backend/src/snipebot/api/settings.py`: nieuw endpoint `POST /settings/test-telegram` dat een testbericht verstuurt op basis van (optioneel) meegegeven settings uit de UI.
  - `frontend/src/api/client.ts`: nieuwe API helper `testTelegramSettings(...)` + payload/response types.
  - `frontend/src/App.tsx`: nieuwe knop **Test Telegram** met loading state en duidelijke success/error feedback.
  - `backend/tests/test_watchlist.py`: nieuwe tests voor success/error response van `/settings/test-telegram`.
  - `frontend/src/App.test.tsx`: settings test uitgebreid met klik op **Test Telegram** en assertie op API call.
- Errordiagnostiek verbeterd voor Telegram testfouten:
  - `backend/src/snipebot/notifications/telegram.py`: HTTPError-responses van Telegram worden nu geparsed op `description`, zodat de UI een concrete providerfout toont i.p.v. alleen `HTTP Error 403`.
  - `backend/tests/test_telegram_notifier.py`: nieuwe test die valideert dat een 403 met JSON-description correct als duidelijke foutmelding wordt teruggegeven.
- Bescherming toegevoegd tegen bot-id als chat-id:
  - `backend/src/snipebot/domain/settings.py`: validatie toegevoegd (`is_bot_chat_id`) die voorkomt dat `telegram_chat_id` gelijk is aan de bot-id uit token tijdens settings save.
  - `backend/src/snipebot/api/settings.py`: `POST /settings/test-telegram` blokkeert direct met duidelijke melding als bot-id als chat-id gebruikt wordt.
  - `frontend/src/App.tsx`: client-side validatie toegevoegd voor Save settings + Test Telegram met directe UX-foutmelding.
  - `backend/tests/test_watchlist.py`: tests toegevoegd voor reject bij save en reject bij test-endpoint met bot-id als chat-id.
  - `frontend/src/App.test.tsx`: test toegevoegd die valideert dat UI deze ongeldige combinatie blokkeert zonder API test-call.

## How to verify
1. Gerichte unit tests:
   - `pytest backend/tests/test_telegram_notifier.py -q`
   - `pytest backend/tests/test_alert_rules.py -q`
2. Worker/alert integratie:
   - `SNIPEBOT_DB_URL="sqlite:////home/mevius/snipebot/.tmp/test.db" .venv/bin/pytest backend/tests/test_price_check_worker.py -q`
3. Brede backend check:
   - `SNIPEBOT_DB_URL="sqlite:////home/mevius/snipebot/.tmp/test.db" .venv/bin/pytest backend/tests -q`
4. Syntax sanity:
   - `python3 -m compileall backend/src backend/tests`
5. Frontend settings test:
   - `cd frontend && npm run test -- App.test.tsx`
6. Telegram test-endpoint (backend):
   - `SNIPEBOT_DB_URL="sqlite:////home/mevius/snipebot/.tmp/test.db" .venv/bin/pytest backend/tests/test_watchlist.py -q -k "settings_test_telegram or settings_get_defaults"`

## Verification evidence
- `pytest backend/tests/test_telegram_notifier.py -q` → geslaagd (`3 passed`).
- `pytest backend/tests/test_alert_rules.py -q` → geslaagd (`3 passed`).
- `python3 -m compileall backend/src backend/tests` → geslaagd (na wijzigingen opnieuw uitgevoerd).
- `python3 -m pip install -e "./backend[dev]"` → niet mogelijk in deze omgeving (`No module named pip`).
- `uv venv .venv` + `uv pip install --python .venv/bin/python -e "./backend[dev]"` → dependency-setup gelukt in lokale venv.
- `SNIPEBOT_DB_URL="sqlite:////home/mevius/snipebot/.tmp/test.db" .venv/bin/pytest backend/tests/test_price_check_worker.py -q` → geslaagd (`7 passed`) na fix voor `app_settings` cleanup.
- `SNIPEBOT_DB_URL="sqlite:////home/mevius/snipebot/.tmp/test.db" .venv/bin/pytest backend/tests -q` → geslaagd (`55 passed, 13 warnings`).
- Na UI-settings uitbreiding opnieuw uitgevoerd:
  - `SNIPEBOT_DB_URL="sqlite:////home/mevius/snipebot/.tmp/test.db" .venv/bin/pytest backend/tests -q` → geslaagd (`56 passed, 13 warnings`).
- Na toevoeging van de test-knop opnieuw uitgevoerd:
  - `SNIPEBOT_DB_URL="sqlite:////home/mevius/snipebot/.tmp/test.db" .venv/bin/pytest backend/tests -q` → geslaagd (`58 passed, 13 warnings`).
- Na verbetering van Telegram 403 error mapping:
  - `.venv/bin/pytest backend/tests/test_telegram_notifier.py -q` → geslaagd (`4 passed`).
  - `SNIPEBOT_DB_URL="sqlite:////home/mevius/snipebot/.tmp/test.db" .venv/bin/pytest backend/tests -q` → geslaagd (`59 passed, 13 warnings`).
- Na toevoeging bot-id/chat-id validatie:
  - `SNIPEBOT_DB_URL="sqlite:////home/mevius/snipebot/.tmp/test.db" .venv/bin/pytest backend/tests -q` → geslaagd (`61 passed, 13 warnings`).
- Frontend tests in deze omgeving niet uitvoerbaar: `npm`/`node` zijn niet beschikbaar (`npm: command not found`).
