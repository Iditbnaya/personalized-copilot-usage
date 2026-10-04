# Reuse the user's browser session

Authentication belongs to a browser profile, not to this skill. A skill cannot
transfer login from a normal browser, an editor, or GitHub CLI into a different
automation profile. Keep authentication in the browser's own private profile;
never serialize it into skill files, screenshots, messages, or a repository.

## GHCP App: establish a usable provider first

GitHub documents MCP servers and canvases as app capabilities, not as one shared
authentication context. Check the actual tools exposed in the current session:

- **App Browser canvas:** inspect `list_canvas_capabilities("browser")`. Its
  `read_page` and `navigate_page` actions may require a `page_id` returned by
  `open_browser_page`. Only use that operation if it is actually exposed and
  follow its current schema. A response containing just `instanceId`, `url`,
  and `input` from `open_canvas` does not supply that required `page_id`.
  Never substitute a canvas instance ID, URL, or guessed value.
- **Failed capability lookup:** an errored or timed-out capability listing is
  `unknown`, not proof that a capability is absent. Retry the lookup once; if
  it fails again, report the tool error rather than mark the provider unsupported
  or ask for login.
- **Missing native discovery:** only a successful capability/tool listing can
  establish that the required page-discovery operation is absent. In that case,
  the native route is tool-unavailable, not signed out. Do not ask the
  user to log in in a canvas whose authenticated state you cannot read.
- **Playwright MCP:** it has its own `browser_tabs`, `browser_navigate`,
  `browser_snapshot`/`browser_find`, and interaction tools. Its tab indices
  and element refs are valid only for that Playwright connection.
- **Provider changes:** if a user is working in the native canvas but only
  Playwright is readable, explain the distinction and ask before switching.
  Never check Playwright to decide whether the native canvas is signed in.
  Opening a native canvas is not a way to bring a Playwright window forward.

Keep the chosen provider and returned page handle/tab identity in conversation
context for the report. Tool listings are session-specific; a missing operation
here is not proof that no app version supports it. Do not guess endpoints or
inspect app internals to bypass missing tool capabilities.

### Incomplete native route: use a complete available alternative

The absence of `open_browser_page` blocks the native `read_page` chain, not
every browser integration. A browser panel merely being open is not an
instruction to use it.

1. If Playwright is already the chosen provider for this task, reuse it first:
   call its `browser_tabs`, select the existing relevant tab, and read/refresh
   it. Do not rediscover the incomplete native route or ask to choose again.
2. If no provider was chosen and the native discovery/read chain is incomplete,
   check whether Playwright's tab discovery, navigation, and snapshot/read tools
   are actually available. If they are, choose Playwright and state which
   browser is being used. This is a first selection, not a silent switch.
3. If the user explicitly asked to use a native/shared tab, or a native
   provider had already been chosen, explain its missing handle capability
   and ask before switching to Playwright. Honor a refusal or native-only request.
4. Once Playwright is chosen, determine authentication only from its own page:
   reuse a valid session or prompt in its window when login is required.
   Never pass Playwright tab indices to native `read_page`.
5. If no complete browser provider is available, name the missing capability
   and return available local results. Do not loop on the same capability
   error, guess `page_id`, claim to have repaired the app integration, or request
   login that the assistant cannot verify.

This fallback changes skill routing, not the app's tool registration. Native
support requires the app to expose its page-discovery operation or a documented
equivalent that actually returns the required handle.

## Current-state decision

Re-evaluate authentication on every account-usage request, after the navigation
or refresh described below. Do not decide from a remembered login, a previous
prompt, an old login-page snapshot, or the mere existence of cookies.

| Observed state after checking GitHub | Action |
|---|---|
| `signed_in`: GitHub accepts the session for the intended account | Reuse the session and read available usage. Do not prompt for login. If the card is missing, report that data limitation without discarding the valid session. |
| `authentication_required`: GitHub displays a login, verification, or SSO challenge | Prompt the user to complete the required authentication in this same browser, wait, then recheck. This applies to both first-time login and expired/revoked sessions. |
| `unknown`: no browser access, loading/error page, or insufficient evidence of identity | Explain or diagnose the specific access problem. Do not infer that the user is logged out or ask them to log in as a generic fix. |
| `account_mismatch`: the session belongs to a different or ambiguous account | Ask the user to confirm/select their intended account before reading usage. Do not silently switch accounts. |

Let the browser reuse cookies automatically on navigation. Valid saved cookies
may restore a session even when no GitHub tab is open. Expired cookies may be
present while authentication is still required. Never inspect, copy, or export
cookie values to distinguish these cases; use GitHub's rendered response.

## Reuse before authenticating

1. Prefer a personal GitHub page already shared/connected through the host's
   supported browser tools. Discover those tools and their page handles; do not
   assume a browser canvas and Playwright use the same session. A canvas opening
   without a readable page handle is not proof of automation access.
2. If using Playwright MCP, call `browser_tabs` with `action: "list"` first.
   Select a relevant existing GitHub tab using its returned index, then read
   its page. If there is no suitable tab, open a page in the SAME configured
   browser profile/context so its saved cookies are reused; a new page is not
   a new profile. Do not launch a separate browser or isolated context merely
   to check usage. If the tool must start a browser, use its existing configured
   persistent profile or supported existing-browser connection.
3. Verify the intended account from the page's rendered identity. If multiple
   accounts are present or an identity conflicts, ask which personal account
   to use. Never switch accounts silently or read another person's usage.
4. Refresh an existing Copilot usage page in the SAME context, or navigate
   the selected page to `https://github.com/settings/copilot`. Use the host's
   reload/navigation tool when available. Read the current rendered card.
   Do not reuse old figures as if they were freshly collected.
   If an old tab is on the login page and no user authentication is currently
   in progress, first navigate once to Copilot settings in the SAME context.
   This lets a session established in another tab or saved cookies take effect
   BEFORE deciding whether to ask for login. Do not interrupt login/SSO while
   the user is completing it.
5. If the card and correct identity are visible, report the values without
   asking for login. A missing card, 403, 404, loading state, network error,
   or browser-tool error does not by itself prove the user is signed out.
   Read the visible card using a fresh accessibility snapshot/ref. The real
   GitHub page can contain both a visible "Usage this cycle" label and the same
   text in a hidden tooltip. A global exact-text locator can fail strict mode.
   Inspect the matches and target the visible card using observed structure;
   do not choose the first arbitrary text match or turn a locator failure into
   a login prompt. Do not hardcode a user-specific heading or transient ref in
   the reusable skill.

Tool names may be prefixed differently in each host. Use available tools, not
invented ones. If shared browser tools need a page ID, obtain it through their
documented page-discovery operation; never use a canvas ID or URL in its place.

### Recover a stale handle without changing the authentication context

After a tab/browser reconnect, a tool can fail with `ERR_ABORTED`, a detached
frame, or a stale page handle before navigation settles. This is `unknown`,
not `authentication_required`. Rediscover the current page using the SAME
provider, retry the intended read/navigation once, and inspect the resulting
page. Do not reset the profile or open another provider to handle it.
If it still fails, report the tool error; do not loop or request login.
Do not navigate over an authentication step the user is actively completing.

## Prompt and recheck when authentication is required

When the current check yields `authentication_required`, ask the user to
complete the visible login, verification, or SSO step in that SAME
automation/shared browser window. Do not ask them to sign in at billing
settings. Leave the window and tab open while waiting. Do not ask for another
login while a usable `signed_in` session is available.

After confirmation, read the SAME page/context again. If it remains on a login
form, navigate once to Copilot settings in that same context and reread it.
Classify the NEW response with the state table: `signed_in` continues without
another prompt; `unknown` reports the access problem; `account_mismatch`
requires account clarification.

If it still yields `authentication_required`, stop the login loop of identical
instructions. Explain that authentication has not reached THIS connected
browser; do not assert a profile mismatch as the only possible cause. Ask the
user to complete the displayed step in this specific connected window or to
connect the browser where they are already signed in. Recheck after that
recovery action. Do not tell the user their password is wrong.

Offer the host's supported "share/connect existing browser tab" mechanism if
one is actually available. Otherwise explain the persistent-profile setup
below. Continue the local model/token report independently.

This is NOT a once-per-conversation login restriction. A later
`authentication_required` state must prompt again when appropriate, even if a
previous report succeeded. The decision follows current authentication, not
prompt history. Never declare success until a fresh page check verifies it.

## Keep authentication in the browser

- Do not call `browser_close`, sign out, clear cookies, clear storage, or reset
  the profile after a report. Respect an explicit user request to close or log
  out, and do not preserve sessions against their wishes.
- Do not read cookies, local storage, credential stores, browser profile files,
  or authentication headers to recover a sign-in. Do not export `storageState`,
  import cookies from another browser, or publish a cookie/storage-state file.
- Do not keep session cookies alive by altering expiry, polling, or bypassing
  GitHub/SSO policy. A revoked or expired session may legitimately need login.
- Revalidate account identity when reusing a session. Remembering a page handle
  within the conversation is fine; remembering that the user was logged in
  is not a substitute for checking the page.

## Persistent Playwright MCP configuration

This is optional host setup, not something SKILL.md can enforce. For users of
the standalone Microsoft Playwright MCP server, its documented
`--user-data-dir` option selects a stable browser profile. Without an explicit
path, default profiles can depend on the workspace, so another project may
look signed out.

In the host's EXISTING Playwright server configuration, retain other settings
and configure an absolute directory private to the current OS user, outside
the repository and cloud-synced folders. Do not combine it with `--isolated`.
The following is a generic configuration example, not an active configuration
or a file to run without replacing `YOUR_USER`:

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": [
        "-y",
        "@playwright/mcp@latest",
        "--user-data-dir",
        "C:\\Users\\YOUR_USER\\AppData\\Local\\personalized-copilot-usage\\browser-profile"
      ]
    }
  }
}
```

On macOS/Linux, use an absolute path in the user's private local application
data directory and restrict directory access to that user. Do not use another
person's profile or a shared service account. Never check the profile into Git.

Use only one running browser instance per profile; do not reuse it across
concurrent agents/users. If a profile is busy, report that conflict rather than
delete it, kill another session, or fall back silently to an empty profile.
Do not enable a shared HTTP browser context or a public remote debugging port.

Apply settings only to the browser provider the host actually uses. A host
with a built-in browser may ignore `mcp-config.json`; changing a separate CLI
configuration will not repair it. Consult the host's browser/profile settings.
If configuration or lifecycle controls are unavailable, say persistence cannot
be configured from this conversation rather than claiming cookies were saved.

For users who want their existing Chrome/Edge sign-in rather than a dedicated
automation profile, Playwright also documents an opt-in browser extension.
Use the supported connection flow with the user's approval; do not extract
their normal browser's cookies. Installation is not automatic.

After configuring the correct provider, the user may need to sign in once in
its profile. Verify the usage page in the same context. Cross-restart retention
is verified only after a user-approved restart of that provider and a fresh
identity/card read. Do not restart unrelated work to test persistence, and do
not claim retention merely because the configuration file was changed.
Distinguish closing/reopening a tab, closing/reconnecting the browser, restarting
the MCP server, and restarting the app. A pass at one boundary does not prove
the others. Check the tool's actual behavior: `browser_close` may close only
the page, not the browser process.

References:
- https://docs.github.com/en/copilot/how-tos/github-copilot-app/customize-github-copilot-app
- https://docs.github.com/en/copilot/how-tos/github-copilot-app/working-with-canvas-extensions
- https://github.com/microsoft/playwright-mcp#user-profile
- https://github.com/microsoft/playwright-mcp#configuration
