# Personalized Copilot Usage

A reusable Copilot skill for understanding **your own recorded model activity**
and, separately, your **GitHub current-cycle credit consumption**.

No Copilot CLI installation or organization billing administrator role is
required. This is an instruction-based skill, not an independent dashboard,
extension, or universal telemetry collector.

## Example report

![Example detailed local model-usage report showing model names, input/output tokens, and cached-read tokens](docs/images/model-usage-example.png)

User-contributed example of the detailed view, not live data. This screenshot
includes optional API-event and session counts; current default reports hide
API-event counts and include a derived total-token column.

## What it can report

| Source | Reports | Requirements |
|---|---|---|
| Local app history | Recorded models, input/output tokens, cached-token counters, daily trends; API-event counts only on explicit request | Host must expose the personal `session_store_sql` tool with the supported local usage schema |
| Copilot settings | Current-cycle credits, displayed limit and reset date when visible | Browser automation tool with the user's authenticated GitHub session |
| Personal billing API, optional | Billing quantities and model aggregates for personally purchased plans | Python 3.9+ and existing authorized GitHub authentication |

**Installing the skill does not add these tools.** The local-history integration
is host-specific: ordinary IDE Copilot installations may not expose
`session_store_sql`. Browser sign-in is independent of editor sign-in.
If a source is unavailable, the skill explains the limitation instead of
inventing metrics.

Local records do not cover all devices, IDEs, or GitHub products. Local model
identifiers may differ from billing model labels. Recorded API events are not
premium requests or AI credits. No token-to-credit conversion is performed.

For organization-managed Business/Enterprise users, the skill uses their own
**Copilot settings > Usage this cycle**, not admin billing APIs. This view may
not provide model-level or historical details.

## Install

Clone this repository, then copy `skills/personalized-usage` into your host's
supported personal skill directory. For Copilot hosts that load personal skills
from `~/.copilot/skills`, use the following.

### Windows PowerShell

```powershell
git clone https://github.com/Iditbnaya/personalized-copilot-usage.git
New-Item -ItemType Directory -Path "$HOME\.copilot\skills" -Force | Out-Null
Copy-Item -LiteralPath ".\personalized-copilot-usage\skills\personalized-usage" `
  -Destination "$HOME\.copilot\skills" -Recurse
```

### macOS / Linux

```bash
git clone https://github.com/Iditbnaya/personalized-copilot-usage.git
mkdir -p ~/.copilot/skills
cp -R personalized-copilot-usage/skills/personalized-usage ~/.copilot/skills/
```

If a skill with that name already exists, review and back it up before replacing
it. Reload or start a new host session to discover the installed skill.
Other hosts may support project-scoped skills in `.github/skills`; consult
their skill-loading documentation. A different installation path does not
make missing history tools available.

## Keep your GitHub sign-in

The skill checks the **current authentication state** on each account-usage
request, using the connected browser's existing profile:

- **Valid session or saved login cookies:** reuse them without prompting for login.
- **No valid session or an expired session:** prompt for the login/verification
  GitHub requires in that same browser, then recheck and continue.
- **Browser or page error:** report the access problem, not a login requirement.

An old login tab or no open GitHub tab does not establish that the user is
signed out: the skill checks Copilot settings with the same profile first.
Cookies are reused by the browser, never read, exported, or cleared by the
skill. Cookie presence alone is not proof of valid authentication.

After you confirm login, it rechecks the same context. If authentication is
still required, it helps identify the correct connected window or unfinished
verification step rather than repeating identical instructions. Later session
expiry can still trigger a new login prompt; there is no once-only restriction.

**Signing in to your normal browser does not sign in a separate automation
browser.** For standalone Playwright MCP, configure a stable, private
`--user-data-dir` outside the repository (without `--isolated`) to retain that
browser's login across reports/projects. Only one browser instance may use
the profile at a time. A built-in host browser needs its own supported profile
settings; a separate CLI configuration may have no effect.

See [Browser session reuse and setup](skills/personalized-usage/references/browser-session.md)
for the configuration example and optional existing-browser connection.
The skill cannot guarantee retention if the host uses temporary profiles or
GitHub/SSO expires the session. Cookies and auth state must never be uploaded
to this repository.

## Use

Invoke `/personalized-usage` in hosts supporting user-invocable skills, or ask:

- "Which models did I use this month?"
- "Show my recorded input and output tokens by model."
- "Show my local usage for the last 7 days."
- "How many AI credits have I used this cycle?"

Model questions use local history first and are not blocked on browser sign-in.
Credit questions use Copilot settings. The reports identify their source,
coverage, period, missing fields, and derived calculations.
Default model tables show **Model | Input tokens | Output tokens | Total tokens | Cached tokens**,
with an overall Total row. Total tokens are derived as input + output; cached
and reasoning counters are not added again. Missing samples are labeled partial.
API-event counts are omitted unless explicitly requested; they remain internal
for checking whether token records are complete.

Overview summaries also include **total AI credits consumed** and **USD usage
cost**, each with its own source, scope, and period. These are shown only from
authorized account data; otherwise they are explicitly unavailable. Managed
users may see credits but not dollar costs. The skill never converts local
tokens to credits or dollars and never requests admin access to fill missing
financial fields. Billed usage cost is separate from gross usage value,
discounts, and subscription fees. A currency-unspecified amount is not labeled USD.

## Optional personal-plan billing script

This adapter is **not for organization-funded Copilot usage**. It requires
Python 3.9+ and uses only the standard library. It uses an existing `GH_TOKEN`
or `GITHUB_TOKEN`, or an already-authenticated `gh` installation if available.
Do not paste tokens into chat or commit them. GitHub's billing documentation
requires a classic PAT; fine-grained PATs are not supported by these endpoints.

```powershell
python .\skills\personalized-usage\scripts\personalized_usage.py --period current-month
```

Other periods: `previous-month`, `today`, `last-7-days`, `last-30-days`, or
`custom --start YYYY-MM-DD --end YYYY-MM-DD` (up to 93 inclusive days).
The adapter resolves the authenticated identity and never accepts a target
username. Personal reports exclude organization/enterprise-funded usage;
an empty report does not mean zero Copilot activity.

## Privacy and accuracy

- Read-only operations; no billing, budget, or account changes.
- No other-user, organization-wide, or administrator-only reporting.
- No credential scraping, undocumented usage endpoints, or raw database access.
- Local history is scoped by the tool to the OS profile, not verified GitHub
  ownership. Shared or ambiguous profiles require a known personal session scope.
- Local reporting uses aggregate metadata, not conversation contents.
- Missing token samples are marked partial, not silently replaced with zero.
- Cached/reasoning counters are not added to input/output totals.
- Remaining against a displayed limit is arithmetic, not a guarantee of
  spendable shared capacity.

Usage values can be sensitive. Review reports before sharing them.
The repository contains reusable instructions, code, synthetic tests, and a
user-contributed example screenshot. It does not collect usage records or
store credentials, browser profiles, or authentication state.

## Development

Run the tests without installing dependencies:

```powershell
python -B -m unittest discover -s .\skills\personalized-usage\tests -v
```

Tests cover identity validation, period validation, unit/model aggregation,
decimal precision, missing data, error handling, non-admin routing, and local
SQL examples against synthetic fixtures. They do not prove browser access or
tool availability in every host.

## Sources

- [Monitoring GitHub AI Credits usage](https://docs.github.com/en/copilot/how-tos/manage-and-track-spending/monitor-ai-usage)
- [Billing usage REST API](https://docs.github.com/en/rest/billing/usage)
- [Automating usage reporting](https://docs.github.com/en/billing/tutorials/automate-usage-reporting)

## License

MIT. This is a community skill, not an official GitHub product.
