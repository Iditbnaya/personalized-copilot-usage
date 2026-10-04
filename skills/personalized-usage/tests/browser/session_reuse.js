// Review before running: code-run tools execute with full server-process privileges.
// Run only in a disposable test browser, never a profile with real sign-ins.
async (page) => {
  const url = new URL(page.url());
  if (url.hostname !== "127.0.0.1" || url.protocol !== "http:" ||
      !url.pathname.startsWith("/fixture/")) {
    throw new Error("Open the loopback synthetic fixture first. Never run on GitHub.");
  }
  const base = url.origin;
  const context = page.context();
  const timeout = 5000;
  function assertTestOnlyPages() {
    for (const candidate of context.pages()) {
      const address = candidate.url();
      if (address === "about:blank") continue;
      const candidateUrl = new URL(address);
      if (candidateUrl.origin !== base || !candidateUrl.pathname.startsWith("/fixture/")) {
        throw new Error("Refusing a browser context with unrelated pages. Use a disposable test browser.");
      }
    }
  }
  assertTestOnlyPages();
  const health = await page.request.get(`${base}/fixture/health`, {timeout});
  if (health.status() !== 200) throw new Error("Fixture health check failed.");
  const marker = await health.json();
  if (marker.fixture !== "personalized-usage" || marker.synthetic !== true) {
    throw new Error("This is not the expected synthetic test server.");
  }
  const ownedPages = [];
  const passed = [];
  let phase = "fixture setup";
  let primaryFailure = null;
  function check(condition, message) {
    if (!condition) throw new Error(message);
  }
  function message(error) {
    return error instanceof Error ? error.message : String(error);
  }
  async function step(name, run) {
    phase = name;
    assertTestOnlyPages();
    await run();
    passed.push(name);
  }
  async function navigate(path, target = page) {
    assertTestOnlyPages();
    return await target.goto(`${base}/fixture/${path}`, {timeout});
  }
  async function isSignedIn(target = page, identity = "demo-user") {
    const locator = target.locator("#identity");
    if (await locator.count() !== 1 || !await locator.isVisible()) return false;
    return await locator.textContent({timeout}) === `Signed in as ${identity}`;
  }
  async function syntheticSessionState(target = page) {
    const response = await target.request.get(`${base}/fixture/session-state`, {timeout});
    check(response.status() === 200, "Fixture session-state check failed.");
    const state = await response.json();
    check(typeof state.cookiePresent === "boolean" && typeof state.authenticated === "boolean",
      "Fixture session-state must return booleans only.");
    return state;
  }
  async function login(target = page) {
    await navigate("login", target);
    await target.getByRole("button", { name: "Sign in as demo-user", exact: true }).click({timeout});
    await target.waitForURL(`${base}/fixture/usage`, {timeout});
    check(await isSignedIn(target), "Expected synthetic identity after sign-in.");
  }
  async function clearFixture() {
    await navigate("cleanup");
    await page.getByRole("button", { name: "Clear synthetic fixture state" }).click({timeout});
    await page.waitForURL(`${base}/fixture/reset`, {timeout});
  }
  try {
    await clearFixture();
    await step("No session: usage redirects to visible login", async () => {
      await navigate("usage");
      check(page.url() === `${base}/fixture/login`, "Expected login redirect.");
      check(await page.getByRole("heading", { name: "Fixture sign in" }).isVisible(),
        "Expected visible login form.");
    });
    await step("Signed-out refresh remains authentication-required", async () => {
      await page.reload({timeout});
      check(await page.getByRole("heading", { name: "Fixture sign in" }).isVisible(),
        "Expected login after refresh.");
    });
    await step("Sign-in completes in the same tab and context", async () => {
      await login();
      check(page.context() === context, "Browser context unexpectedly changed.");
    });
    await step("Hidden tooltip duplicate does not make the visible card ambiguous", async () => {
      check(await page.getByText("Usage this cycle", {exact: true}).count() === 2,
        "Fixture must reproduce duplicate visible/hidden text.");
      const visibleLabel = page.getByText("Usage this cycle", {exact: true}).filter({visible: true});
      check(await visibleLabel.count() === 1, "Expected exactly one visible usage label.");
      await visibleLabel.waitFor({state: "visible", timeout});
      check(await page.locator("#credits").isVisible(), "Expected the visible usage card.");
    });
    await step("Same-tab refresh reuses authentication and reads fresh content", async () => {
      const before = Number(await page.locator("#revision").textContent({timeout}));
      await page.reload({timeout});
      check(await isSignedIn(), "Sign-in lost on refresh.");
      check(Number(await page.locator("#revision").textContent({timeout})) > before,
        "Page was not freshly served.");
    });
    await step("New tab reuses saved authentication in the same context", async () => {
      const second = await context.newPage();
      ownedPages.push(second);
      await navigate("usage", second);
      check(await isSignedIn(second), "New tab lost the existing authentication.");
    });
    await step("Old login page does not override an active session", async () => {
      await navigate("login");
      check(await page.getByRole("heading", { name: "Fixture sign in" }).isVisible(),
        "Expected stale login page.");
      await navigate("usage");
      check(await isSignedIn(), "Checking usage should reuse the active session.");
    });
    await step("Valid identity with missing usage card stays signed in", async () => {
      await navigate("no-card");
      check(await isSignedIn(), "Expected valid identity.");
      check(await page.locator("#credits").count() === 0, "Expected missing card.");
    });
    for (const [path, status] of [["forbidden", 403], ["not-found", 404], ["unavailable", 503]]) {
      await step(`HTTP ${status} is observable without treating it as a login`, async () => {
        const response = await navigate(path);
        check(response.status() === status, `Expected HTTP ${status}.`);
        check(await page.getByRole("heading", { name: "Fixture sign in" }).count() === 0,
          "Error response must not look like the fixture login form.");
      });
    }
    await step("Alternate account is distinguishable from the intended account", async () => {
      await navigate("login");
      await page.getByRole("button", { name: "Sign in as other-demo-user", exact: true }).click({timeout});
      await page.waitForURL(`${base}/fixture/usage`, {timeout});
      check(await isSignedIn(page, "other-demo-user"), "Expected different identity.");
      check(!await isSignedIn(), "Must not mistake this for the intended account.");
    });
    await step("Server-revoked session requires login despite retained cookie", async () => {
      const before = await syntheticSessionState();
      check(before.cookiePresent && before.authenticated,
        "Expected a present, accepted synthetic cookie before revocation.");
      await page.getByRole("button", { name: "Revoke fixture session" }).click({timeout});
      await page.waitForURL(`${base}/fixture/login`, {timeout});
      const after = await syntheticSessionState();
      check(after.cookiePresent && !after.authenticated,
        "Revocation must reject a still-present synthetic cookie, not clear it.");
      check(await page.getByRole("heading", { name: "Fixture sign in" }).isVisible(),
        "Expected login when the server rejects the retained synthetic cookie.");
    });
    await step("Reauthentication after revocation succeeds", async () => {
      await login();
    });
    await step("Verification challenge is visible and can complete in the same tab", async () => {
      await page.getByRole("button", { name: "Require fixture verification" }).click({timeout});
      await page.waitForURL(`${base}/fixture/verification`, {timeout});
      check(await page.getByRole("heading", { name: "Fixture verification required" }).isVisible(),
        "Expected visible verification challenge.");
      await page.getByRole("button", { name: "Complete fixture verification" }).click({timeout});
      await page.waitForURL(`${base}/fixture/usage`, {timeout});
      check(await isSignedIn(), "Expected sign-in after verification.");
    });
    await step("No open usage tab: cookie still reuses the session on next navigation", async () => {
      for (const other of ownedPages) await other.close();
      ownedPages.length = 0;
      await page.goto("about:blank", {timeout});
      const next = await context.newPage();
      ownedPages.push(next);
      await navigate("usage", next);
      check(await isSignedIn(next), "Session should survive closing fixture usage tabs.");
    });
  } catch (error) {
    primaryFailure = new Error(`Browser case "${phase}" failed: ${message(error)}`, {cause: error});
  }
  const cleanupErrors = [];
  for (const other of ownedPages) {
    try {
      if (!other.isClosed()) await other.close();
    } catch (error) {
      cleanupErrors.push(new Error(`Closing fixture tab failed: ${message(error)}`, {cause: error}));
    }
  }
  try {
    await clearFixture();
  } catch (error) {
    cleanupErrors.push(new Error(`Clearing synthetic fixture state failed: ${message(error)}`, {cause: error}));
  }
  if (primaryFailure && cleanupErrors.length) {
    throw new AggregateError(
      [primaryFailure, ...cleanupErrors],
      `${primaryFailure.message}; cleanup also failed: ${cleanupErrors.map(message).join("; ")}`,
      {cause: primaryFailure},
    );
  }
  if (primaryFailure) throw primaryFailure;
  if (cleanupErrors.length) {
    throw new AggregateError(cleanupErrors, `Browser cleanup failed: ${cleanupErrors.map(message).join("; ")}`);
  }
  return {
    scope: "Disposable Playwright test browser, synthetic loopback data only",
    passedCount: passed.length,
    passed,
    notVerified: [
      "GitHub live authenticated usage",
      "GHCP App native canvas read_page handle discovery",
      "Cookie persistence across browser/process/app restarts",
      "Agent adherence to skill instructions",
    ],
  };
}
