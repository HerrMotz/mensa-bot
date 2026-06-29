You are a senior software architect and full-stack developer. Help me design and implement a German-language Element/Matrix bot for the Mensas of Studierendenwerk Thüringen.

Project goal:
Create a Matrix/Element bot for one group chat. The bot should show the current relevant meals for selected Mensas in Jena and let the group vote on which Mensa to visit. Voting must use instant-runoff voting / ranked-choice voting. Voting results, including voter names and rankings, should be visible publicly in the chat.

Default scope:
The default configuration should include only these Jena Mensas:

* Philosophenweg
* Universitätshauptgebäude
* Ernst-Abbe-Platz

This list must be configurable so other Mensas can be added later.

Language:
The bot must respond in German.

Target platform:

* Element/Matrix group chat
* One Matrix room only
* Deployment on a VPS
* I do not yet have a Matrix bot account, so setup instructions must include creating/registering one

Core user flow:

1. A user writes a command such as `!mensa`.
2. The bot replies in German with the current relevant meal offerings for the configured Jena Mensas.
3. The bot includes the meal names and prices for:

   * Studierende
   * Bedienstete
4. A user can start a vote with `!mensa votieren`.
5. The bot starts a Matrix-native poll or the best technically feasible Matrix-based equivalent.
6. Users submit ranked preferences for the Mensas.
7. The bot evaluates the result using instant-runoff voting.
8. The bot publicly posts the evaluated result, including:

   * winner
   * IRV elimination rounds
   * current or final rankings
   * which users voted for which ranking
9. Only one vote may be active in the room at a time.
10. The vote closes automatically after 20 minutes by default. This duration must be configurable.

Meal-time logic:
The bot should automatically decide which meal period to show based on the current time.

Expected behavior:

* Before lunch time: show lunch offerings.
* During or shortly after lunch time, before Zwischenversorgung: still show lunch offerings.
* After lunch and when Zwischenversorgung is relevant: show Zwischenversorgung.
* If later meal periods exist, apply the same logic to show the currently appropriate or next useful meal period.
* The exact meal-time boundaries must be configurable.
* Default timezone: `Europe/Berlin`.

Data source:
Use the official Studierendenwerk Thüringen Mensa pages, for example:
https://www.stw-thueringen.de/mensen/jena/mensa-uni-hauptgebaeude.html

Before implementing scraping, investigate whether the site uses a public or semi-structured API/JSON endpoint for the meal plan data. Prefer structured API data over HTML scraping. If scraping is required, make it resilient to layout changes.

Functional requirements:

* Fetch current meals for the configured Jena Mensas.
* Display only prices for Studierende and Bedienstete.
* Do not display guest prices.
* Support configurable Mensa list.
* Support configurable meal-time windows.
* Support configurable vote duration, defaulting to 20 minutes.
* Support one Matrix room only.
* Support one active vote at a time.
* Persist active vote state so the bot can recover after restart.
* Cache fetched menu data to avoid unnecessary requests.
* Handle unavailable Mensa pages, missing meals, holidays, closed Mensas, and missing prices gracefully.
* German umlauts and special characters must work correctly.

German commands:

* `!mensa` — zeigt die aktuellen relevanten Speisen der konfigurierten Mensen
* `!mensa heute` — zeigt die heutigen Speisen
* `!mensa votieren` — startet eine Abstimmung über die konfigurierten Mensen
* `!mensa ergebnis` — zeigt das aktuelle ausgewertete Abstimmungsergebnis
* `!mensa schließen` — schließt die aktuelle Abstimmung manuell
* `!mensa hilfe` — zeigt die verfügbaren Befehle

Voting requirements:
Use instant-runoff voting / ranked-choice voting.

There should be no “egal” / “mir egal” option.

Voting should be Matrix-native where feasible. Since native Matrix polls probably do not support ranked choices directly, design a smart workaround.

Recommended default voting design:
For the default three Mensas, generate all possible ranking permutations and use those as the options in a native Matrix poll.

Example poll options:

1. Philosophenweg > Universitätshauptgebäude > Ernst-Abbe-Platz
2. Philosophenweg > Ernst-Abbe-Platz > Universitätshauptgebäude
3. Universitätshauptgebäude > Philosophenweg > Ernst-Abbe-Platz
4. Universitätshauptgebäude > Ernst-Abbe-Platz > Philosophenweg
5. Ernst-Abbe-Platz > Philosophenweg > Universitätshauptgebäude
6. Ernst-Abbe-Platz > Universitätshauptgebäude > Philosophenweg

Each user selects exactly one ranking option. The bot reads the poll responses, maps each selected option back to a ranked ballot, and evaluates all ballots using instant-runoff voting.

This works well for three Mensas because there are only six possible rankings. The implementation must document that the permutation approach becomes impractical for many Mensas because the number of options grows factorially. If the configured Mensa list grows beyond a configurable threshold, such as four Mensas, the bot should fall back to a command-based ranked ballot system, for example:
`!mensa wahl 2,1,3`

Even in fallback mode, the bot should still post a Matrix message that clearly explains the options and current vote state.

Public voter visibility:
The bot must publicly show voter names and their selected ranking in the result message.

Example:

* Anna: Philosophenweg > Ernst-Abbe-Platz > Universitätshauptgebäude
* Max: Universitätshauptgebäude > Philosophenweg > Ernst-Abbe-Platz

The bot should use Matrix display names where available and Matrix user IDs as fallback.

Instant-runoff evaluation:
Implement IRV as follows:

1. Count each ballot’s highest-ranked active option.
2. If one Mensa has more than 50% of active votes, it wins.
3. Otherwise eliminate the Mensa with the fewest votes.
4. Transfer ballots for the eliminated Mensa to the next still-active ranked Mensa.
5. Repeat until a winner exists.
6. Handle ties deterministically and document the tie-breaking rule.

Tie-breaking:
Ask for a final tie-breaking preference before implementation. If none is provided, use this default:

1. Prefer the Mensa with more first-choice votes in the original round.
2. If still tied, prefer the Mensa with the better total ranking score.
3. If still tied, choose deterministically by configured Mensa order.
4. Always show that a tie-break was used.

Result display:
The result message should be in German and show:

* status: offen or geschlossen
* time remaining, if open
* each voter’s ranking
* IRV round-by-round counts
* eliminated Mensas per round
* final winner
* tie-break explanation, if applicable

Architecture requirements:
Propose a suitable stack for VPS deployment. Consider:

* Python with matrix-nio
* Node.js with matrix-bot-sdk
* SQLite for persistence
* Docker and docker-compose for deployment

The implementation should include:

* Bot service
* Matrix client integration
* Mensa data fetcher/parser
* Meal-time selector
* Matrix poll integration
* Vote manager
* Instant-runoff vote evaluator
* SQLite database
* Configuration file
* Dockerfile
* docker-compose.yml
* Logging
* Tests

Configuration should include:

* Matrix homeserver URL
* Matrix bot username/access token or login credentials
* Matrix room ID
* command prefix, default `!mensa`
* configured Mensas
* Mensa URLs or identifiers
* meal-time windows
* default vote duration, default 20 minutes
* maximum Mensa count for poll-permutation voting
* cache duration
* timezone, default `Europe/Berlin`

Database schema:
Design tables for:

* mensas
* menu_cache
* meals
* room_config
* vote_sessions
* vote_options
* vote_ballots
* matrix_poll_events
* bot_state

Edge cases:

* Website unavailable
* No menu for today
* Mensa closed
* Prices missing
* Matrix poll data incomplete
* Element client does not display the poll as expected
* User changes vote
* User votes twice
* User changes display name
* Bot restarts during active vote
* Vote auto-close time passes while bot is offline
* Another vote is started while one is active
* Matrix homeserver rate limits requests
* Preferential result is tied
* Only one user votes
* No users vote
* A configured Mensa is renamed
* More Mensas are configured than can reasonably fit into permutation-based poll options

Deliverables:

1. Ask any remaining clarification questions before implementation.
2. Recommend the technical architecture.
3. Investigate the Studierendenwerk Thüringen data source.
4. Investigate Matrix poll support and the exact Matrix event types needed.
5. Propose the final voting interaction design.
6. Define the German bot commands.
7. Define the database schema.
8. Implement the bot.
9. Provide Docker-based VPS deployment instructions.
10. Include instructions for creating/registering the Matrix bot account.
11. Include tests for:

    * Mensa data fetching/parsing
    * meal-time selection
    * command parsing
    * Matrix poll handling
    * instant-runoff evaluation
    * persistence and restart recovery
12. Include documentation for configuration and operation.

Before writing code, ask only about unresolved technical choices, especially:

* preferred homeserver
* whether bot registration is open or requires admin registration
* final tie-breaking preference
* whether automatic vote result updates should be posted periodically or only on `!mensa ergebnis` and vote close

