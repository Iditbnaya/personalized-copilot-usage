# Browser integration validation

Checked on 2026-10-04 in one Windows GitHub Copilot App session. This is not a
claim of compatibility with every app version or browser provider. No GitHub
cookies, tokens, personal usage values, or account identifiers are stored here.

## Documentation cross-check

| First-party source | What it establishes |
|---|---|
| [GitHub App customization](https://docs.github.com/en/copilot/how-tos/github-copilot-app/customize-github-copilot-app) | The app supports skills, MCP servers, and canvases. Repository/CLI MCP configurations are available in the app, and installed integrations can be managed through Customize. |
| [GitHub App canvases](https://docs.github.com/en/copilot/how-tos/github-copilot-app/working-with-canvas-extensions) | Canvas capabilities must be exposed as callable actions. A rendered panel alone does not specify its browser API, page-ID contract, or authentication sharing. |
| [GitHub AI usage](https://docs.github.com/en/copilot/how-tos/manage-and-track-spending/monitor-ai-usage) | Business/Enterprise users can view their own current-cycle consumption through Copilot settings, without admin billing access. |
| [Microsoft Playwright MCP profiles](https://github.com/microsoft/playwright-mcp#user-profile) | Persistent profiles, isolated sessions, and an opt-in connection to an existing browser are different modes. Explicit user-data directories control persistent profiles; concurrent browsers must not share one. |

The public GitHub docs inspected did not define `open_browser_page` or the
native browser canvas's cookie-persistence contract. Do not apply Copilot cloud
agent browser restrictions to the desktop app, or present Playwright-specific
flags as guarantees for a native canvas.

## Actual tool-contract findings

- The native browser canvas exposed `read_page`/`navigate_page` requiring a
  `page_id` from `open_browser_page`. That discovery operation was not exposed
  to this session. `open_canvas` returned an instance handle and URL, not the
  required page ID. No guessed IDs were submitted.
- Opening a native diagnostic panel at example.com did not add that page to
  the Playwright tab listing. The two surfaces must not be treated as one.
- Native canvas reading is therefore **blocked in this tool configuration**.
  Native authentication and cross-restart persistence remain **unverified**.
  This is not evidence that the user is signed out in that canvas.
- Playwright's tab discovery, navigation, accessibility reads, clicks, and
  same-context page operations were callable and tested.

## Results and limits

| Test boundary | Result |
|---|---|
| Real GitHub, initially signed out | Copilot settings redirected to a visible login page. |
| User completes real login in Playwright | Intended personal identity and usage card verified. No password or cookie read by the agent. |
| Real GitHub page refresh | Identity and card remained available; no new login needed. |
| Real GitHub new tab in the same context | Existing authenticated session reused. Test tab closed afterward. |
| Close/reopen the only real GitHub tab | Authentication retained; not by itself proof of a browser-process restart. |
| User-approved `Browser.close()` and browser reconnection | Authentication retained after one transient navigation recovery. No profile configuration changes were made. |
| First navigation after browser reconnection | `ERR_ABORTED` / detached-frame error occurred. Tab rediscovery plus one navigation retry recovered without login. |
| Global exact-text usage label selector | Initially failed strict mode: visible label and hidden tooltip shared text. Inspecting visibility and selecting the visible label fixed the check. |
| Separate MCP calls using synthetic sign-in | Navigate, find, click, new-tab, and find calls preserved the synthetic session between tool invocations. |
| Initial synthetic Playwright suite (before review) | 16 checks passed twice. Review identified gaps in cookie-retention proof, fixture markup, and safe execution instructions; these initial passes do not validate the corrected suite. |
| Fixture repeatability | Initial repeat timed out on a health request. A single-threaded test server could block on a browser's idle preconnection; a threaded server and idle-socket regression fixed this. |
| Initial Python tests (before review) | 27 passed: API/SQL behavior, instruction-content assertions, and the fixture preconnection regression. These are not live browser tests. |
| Native canvas, MCP-process restart, or full app restart | Not validated. Do not infer these from Playwright browser reconnection. |
| Agent compliance with all skill instructions | Not established by these tests. Instructions are not an executable authentication adapter. |

The real GitHub account and browser were left signed in. Synthetic sessions
were cleared and their owned tabs/server stopped. No browser profile was
exported or copied.

## Review corrections and revalidation

All six review findings were addressed locally:

| Finding | Correction and evidence |
|---|---|
| Unsafe code-run context and missing disclosure | Added the RCE-equivalent warning, trusted-source review requirement, disposable-browser requirement, and a guard rejecting unrelated open pages before requests or navigation. Browser revalidation used a newly launched Chrome process and fresh isolated context, not the account browser. |
| Cookie retention not asserted | The fixture reports only boolean cookie-present/authenticated state. The suite asserts present/accepted before revocation and present/rejected afterward. A fault-injected missing-cookie response correctly causes failure. |
| Hidden tooltip fixture did not match the real shape | Fixture now uses a visible span and hidden h4. The suite requires two text matches but exactly one visible match using a visibility filter. |
| Capability lookup failure mistaken for absent capability | Guidance now treats lookup errors as unknown, retries once, and only infers absence from a successful listing. Instruction regression added. |
| Cleanup could replace the primary failure | Named failures retain the original cause; cleanup failures are collected and surfaced alongside it. Missing identity is checked immediately, with explicit timeouts on waiting operations. Combined-error and cleanup-only fault checks pass. |
| Ambiguous CI coverage | README now distinguishes Python fixture regressions and Node test-double checks (in CI) from the opt-in live browser suite (not in CI). |

After correction, **30 Python tests and 6 Node tests passed**. The corrected
**16-case browser suite passed twice consecutively**, and again after fault
injection to verify recovery. The unrelated-page and non-fixture-page guards
also rejected deliberately invalid test contexts. Cookie values were never
read by the browser driver; diagnostics were fixture-side booleans only.

These checks did not repeat real-account login or native-canvas tests. They
do not upgrade the unverified boundaries listed above. Disposable test
browsers and the fixture server were closed; the real account browser was
not navigated, read, or closed during this revalidation.

## Repeat the synthetic browser checks

**Security warning:** `browser_run_code_unsafe` and equivalent code-run tools
execute arbitrary JavaScript with the Playwright server process's privileges
(RCE-equivalent). A script can access browser contexts, cookies, files, and
network resources. Review the entire script from a trusted checkout BEFORE
running it; a loopback URL check does not make downloaded code safe.

**Use a fresh, disposable test browser with no real sign-ins.** Do not run the
suite in the browser/profile used for GitHub, work accounts, or personal sites.
Closing those tabs is not sufficient: a profile can retain cookies from closed
tabs. Do not import storage state, connect to your normal browser, or reuse an
authenticated `--user-data-dir`. Browser isolation protects against accidental
session mixing; it is not a sandbox for the code-run tool's OS privileges.

For a separate standalone Playwright MCP test provider, use `--isolated` with
no storage-state or user-data-dir arguments. Alternatively, a trusted local
test driver can launch a fresh browser and isolated context and pass only its
synthetic page to the suite. Leave your normal account browser untouched.
The shipped suite rejects any open page outside its exact loopback fixture
origin/path (except `about:blank`) before making requests or changing pages.
This guard is defense in depth, not proof that the profile has no credentials,
and cannot protect against a maliciously modified script.

Prerequisites: Python 3.9+, and a disposable Playwright MCP test provider exposing
a code-run tool. The suite uses its provided Playwright `page`; no additional
Python package is needed. Playwright must support `locator.filter({visible: true})`.
Never run fixture-login actions on GitHub or other real services.

1. Start the fixture in a terminal from the repository root:

   ```powershell
   python -B .\skills\personalized-usage\tests\browser\fixture_server.py
   ```

   It binds only to `127.0.0.1`, chooses a free port, and prints its URL.
2. Use the disposable TEST provider's `browser_tabs` to open the returned URL.
   Stop if this provider has any real sign-ins or unrelated pages. Do not close
   or log out of your normal browser to make it pass this check.
3. Pass `skills/personalized-usage/tests/browser/session_reuse.js` to that
   provider's code-run tool using `filename` (use host-native path separators).
   Alternatively load the function through the tool's supported `code` input.
   The suite checks all open pages, the loopback origin, and fixture identity
   before acting. It verifies revocation through fixture-side boolean
   `cookiePresent`/`authenticated` diagnostics, without reading cookie values
   or accessing a browser cookie jar.
4. Read the result's `passedCount`, cases, and explicit unverified boundaries.
   Repeat it on the same fixture tab to check cleanup and repeatability.
5. Close the disposable test browser and stop the fixture server. The suite
   clears only its synthetic cookie via the fixture form. Both primary and
   cleanup failures are reported if cleanup fails; never report a failed
   cleanup as a successful run.

The fixture and suite test browser mechanics, not GitHub's authentication
implementation. Do not use their synthetic numbers as report values.

## Automated regressions versus live browser checks

The Python suite includes the loopback fixture server's threading, boolean
session diagnostics, and visible-span/hidden-heading markup regressions; these
run in CI. The Node built-in test runner also checks the suite's page guard,
missing-identity handling, and error preservation with test doubles:

```powershell
node --test .\skills\personalized-usage\tests\browser\session_reuse.test.cjs
```

These Node tests run in CI without a browser or additional packages. The
opt-in browser suite above does NOT run in the current CI workflow. Neither
the test doubles nor the browser mechanics tests prove agent compliance with
the skill's natural-language decision table.

## Release gate

Keep provider-specific claims bounded to the results above. For native-canvas
support, first obtain a real page-discovery tool and verify read/navigation
against its returned handle. For app/MCP restart guarantees, obtain user
approval and test those exact boundaries. Do not publish a claim of universal
login persistence based on passing instruction-text assertions.
