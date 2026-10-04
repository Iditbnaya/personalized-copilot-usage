# Reuse the user's browser session

Authentication belongs to a browser profile, not to this skill. A skill cannot
transfer login from a normal browser, an editor, or GitHub CLI into a different
automation profile. Keep authentication in the browser's own private profile;
never serialize it into skill files, screenshots, messages, or a repository.

## Reuse before authenticating

1. Prefer a personal GitHub page already shared/connected through the host's
   supported browser tools. Discover those tools and their page handles; do not
   assume a browser canvas and Playwright use the same session. A canvas opening
   without a readable page handle is not proof of automation access.
2. If using Playwright MCP, call `browser_tabs` with `action: "list"` first.
   Select a relevant existing GitHub tab using its returned index, then read
   its page. Do not open another browser or create an isolated context.
3. Verify the intended account from the page's rendered identity. If multiple
   accounts are present or an identity conflicts, ask which personal account
   to use. Never switch accounts silently or read another person's usage.
4. Refresh an existing Copilot usage page in the SAME context, or navigate
   the selected page to `https://github.com/settings/copilot`. Use the host's
   reload/navigation tool when available. Read the current rendered card.
   Do not reuse old figures as if they were freshly collected.
5. If the card and correct identity are visible, report the values without
   asking for login. A missing card, 403, 404, loading state, network error,
   or browser-tool error does not by itself prove the user is signed out.

Tool names may be prefixed differently in each host. Use available tools, not
invented ones. If shared browser tools need a page ID, obtain it through their
documented page-discovery operation; never use a canvas ID or URL in its place.

## Handle an actual sign-in page once

Only when the connected page visibly shows a GitHub login, verification, or
SSO challenge, ask the user to complete it in that SAME automation/shared
browser window. Do not ask them to sign in at billing settings. Leave the
window and tab open while waiting.

After confirmation, read the SAME page/context again. If it remains on a login
form, navigate once to Copilot settings in that same context and reread it.
If authentication is still absent, stop the login loop. Explain that the
connected browser does not have the reported sign-in; this may be a different
profile/window, an expired session, or an incomplete verification step.
Do not tell the user their password is wrong or keep requesting another login.

Offer the host's supported "share/connect existing browser tab" mechanism if
one is actually available. Otherwise explain the persistent-profile setup
below. Continue the local model/token report independently.

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

References:
- https://github.com/microsoft/playwright-mcp#user-profile
- https://github.com/microsoft/playwright-mcp#configuration
