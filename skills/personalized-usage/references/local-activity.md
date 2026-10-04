# Personal local model activity

## Authorized tool and scope

Use `session_store_sql` with `source: "local"` for the current user's local app
history. No CLI installation, browser login, billing role, or raw database
access is needed. Do not switch to organization/repository/shared scopes.
Do not accept another user's account, profile path, or database as a target.
This is a local OS-profile history source, not cryptographically verified
GitHub-account ownership. If the profile is shared or history ownership is
uncertain, ask for a known personal session scope rather than disclose all
history. Do not claim this report covers every device, IDE, or GitHub product.

Use aggregate metadata only. Do not read prompts, responses, paths, repository
names, API endpoints, internal cost/multiplier fields, or token_details_json.
Return model identifiers as recorded; do not map Auto to a guessed fixed model.
Recorded runtime identifiers need not match GitHub billing model labels.

## Discover before querying

First inspect only the relevant table definitions:

```sql
SELECT name, sql FROM sqlite_master
WHERE type = 'table'
AND name IN ('assistant_usage_events', 'sessions')
LIMIT 5
```

The observed local table has `session_id`, `model`, `created_at`, input/output
tokens, cache read/write tokens, and reasoning tokens. Adapt to the returned
schema; missing columns are unavailable, not zeros. If the table is absent,
report that this host does not expose local usage events. Do not fall back to
shell SQLite access or attempt to recreate it.

## Ranges and bounded queries

Default to month-to-date for a usage overview. Resolve explicit today, last 7
days, last 30 days, previous month, or custom range. State date boundaries,
timezone and collection time. Local event timestamps may mix SQLite UTC and
ISO formats; compare 10-character date prefixes, not mixed raw timestamps.
The examples use UTC calendar dates with an exclusive upper boundary. Do not
claim exact local-hour coverage from date-prefix filtering. For an exact
non-UTC range, normalize timestamps with supported SQLite functions after
confirming the stored format, or state the limitation.

Replace START_DATE and END_EXCLUSIVE with validated ISO dates determined from
the user's request and current date. Never interpolate arbitrary user SQL.
If the user requests a session filter, constrain by a verified personal
session ID in addition to the date range. Always include a LIMIT.

### Models and tokens

```sql
SELECT model,
       COUNT(*) AS recorded_api_events,
       COUNT(DISTINCT session_id) AS recorded_sessions,
       SUM(input_tokens) AS input_tokens,
       COUNT(input_tokens) AS input_samples,
       SUM(output_tokens) AS output_tokens,
       COUNT(output_tokens) AS output_samples,
       SUM(cache_read_tokens) AS cache_read_tokens,
       COUNT(cache_read_tokens) AS cache_read_samples,
       SUM(cache_write_tokens) AS cache_write_tokens,
       COUNT(cache_write_tokens) AS cache_write_samples,
       SUM(reasoning_tokens) AS reasoning_tokens,
       COUNT(reasoning_tokens) AS reasoning_samples,
       MIN(created_at) AS first_recorded,
       MAX(created_at) AS last_recorded
FROM assistant_usage_events
WHERE substr(created_at, 1, 10) >= 'START_DATE'
  AND substr(created_at, 1, 10) < 'END_EXCLUSIVE'
GROUP BY model
ORDER BY recorded_api_events DESC
LIMIT 50
```

If 50 rows are returned, query the distinct model count using the same date
filter to determine whether the table is truncated. Do not present a capped
table as complete; retrieve remaining groups or report truncation.

### Daily trend, only when requested

```sql
SELECT substr(created_at, 1, 10) AS day,
       COUNT(*) AS recorded_api_events,
       SUM(input_tokens) AS input_tokens,
       COUNT(input_tokens) AS input_samples,
       SUM(output_tokens) AS output_tokens,
       COUNT(output_tokens) AS output_samples
FROM assistant_usage_events
WHERE substr(created_at, 1, 10) >= 'START_DATE'
  AND substr(created_at, 1, 10) < 'END_EXCLUSIVE'
GROUP BY substr(created_at, 1, 10)
ORDER BY day
LIMIT 93
```

Limit daily requests to 93 inclusive days, or explicitly report truncation.
Days with no rows have no recorded events, not proven zero account-wide usage.

### Highest-activity sessions, only when requested

```sql
SELECT session_id, COUNT(*) AS recorded_api_events,
       SUM(input_tokens) AS input_tokens,
       COUNT(input_tokens) AS input_samples,
       SUM(output_tokens) AS output_tokens,
       COUNT(output_tokens) AS output_samples,
       MIN(created_at) AS first_recorded,
       MAX(created_at) AS last_recorded
FROM assistant_usage_events
WHERE substr(created_at, 1, 10) >= 'START_DATE'
  AND substr(created_at, 1, 10) < 'END_EXCLUSIVE'
GROUP BY session_id
ORDER BY recorded_api_events DESC
LIMIT 10
```

Label this "Top 10 by recorded API events", not top billed consumption.
Use session IDs or anonymous session labels; do not load conversation content
to label them. Request totals separately if needed rather than treating top 10
as the complete population.

## Interpretation and calculations

- Recorded event and token fields are local telemetry, not billing invoices.
- An API event is not a user prompt, premium request, or AI credit. It can
  include internal iterations, retries, and delegated work that was recorded.
- SQL sums are derived aggregates of recorded numeric fields. A field is
  complete only when its sample count equals recorded_api_events. Otherwise
  mark its sum as partial, e.g. "recorded on 8 of 10 events". All-null sums
  are unavailable; never COALESCE missing token counts to zero.
- Input and output totals are separate. If complete and nonnegative, their
  sum may be shown as "input + output (derived)", not a backend total-token
  metric. Do not add cached or reasoning counters to that sum: the categories
  may overlap and telemetry semantics are not established by column names.
- Cached/reasoning fields may be shown separately as recorded counters, with
  overlap/semantics unspecified. Negative or otherwise invalid counts must
  be flagged, not silently corrected or used for percentages.
- No billed credits, remaining account quota, organization totals, or costs
  can be calculated from these events.
- Empty queries mean no local records in the requested range, not no Copilot
  use. Missing history, retention, multiple devices, or incomplete logging can
  limit coverage. Report observed first/last records, not guaranteed retention.
- Never use session-level cloud `session_usage` aggregates to calculate daily
  consumption by filtering only last_used_at: those rows summarize whole
  sessions. Do not merge cloud and local rows, which can duplicate events.

## Output

Lead with **Local Copilot app activity**, requested date range and collection
time. Use a model table with model, input tokens, output tokens and
cache read tokens. Keep event counts internal for completeness checks; do not
display them unless the user explicitly asks for API-call/event counts.
Include other fields only when useful to the question.
Footnote that the report covers available local records only, and is not
account-wide billing usage. If a browser credit card is available, show it in
a separate **GitHub current-cycle credits** section with its own period.
