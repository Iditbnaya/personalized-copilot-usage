const assert = require("node:assert/strict");
const {readFileSync} = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = readFileSync(path.join(__dirname, "session_reuse.js"), "utf8");
const runSuite = vm.runInNewContext(`(${source})`, {URL, Error, AggregateError});
const base = "http://127.0.0.1:12345";

function stubPage({url = `${base}/fixture/login`, extraUrl, gotoErrors = [],
                   marker = {fixture: "personalized-usage", synthetic: true}} = {}) {
  const calls = {requests: 0, navigations: 0, identityReads: 0, clearClicks: 0};
  let current = url;
  const page = {
    url: () => current,
    request: {get: async (_url, options) => {
      assert.equal(options.timeout, 5000);
      calls.requests++;
      return {status: () => 200, json: async () => marker};
    }},
    context: () => ({
      pages: () => extraUrl ? [page, {url: () => extraUrl}] : [page],
    }),
    goto: async (target, options) => {
      assert.equal(options.timeout, 5000);
      const error = gotoErrors[calls.navigations++];
      if (error) throw error;
      current = target.endsWith("/usage") ? `${base}/fixture/login` : target;
    },
    reload: async (options) => { assert.equal(options.timeout, 5000); },
    waitForURL: async () => {},
    getByRole: (_role, options) => ({
      isVisible: async () => true,
      click: async (clickOptions) => {
        assert.equal(clickOptions.timeout, 5000);
        if (options.name === "Clear synthetic fixture state") {
          calls.clearClicks++;
          current = `${base}/fixture/reset`;
        } else {
          current = `${base}/fixture/usage`;
        }
      },
    }),
    locator: () => ({
      count: async () => 0,
      textContent: async () => {
        calls.identityReads++;
        throw new Error("Must not wait for a missing identity");
      },
    }),
  };
  return {page, calls};
}

test("rejects a non-fixture active page before requests or navigation", async () => {
  const {page, calls} = stubPage({url: "https://example.test/account"});
  await assert.rejects(runSuite(page), /Open the loopback synthetic fixture first/);
  assert.equal(calls.requests, 0);
  assert.equal(calls.navigations, 0);
});

test("rejects unrelated tabs before accessing the fixture", async () => {
  for (const extraUrl of ["https://github.com/settings/copilot", "http://127.0.0.1:9999/fixture/login",
                         `${base}/non-fixture`]) {
    const {page, calls} = stubPage({extraUrl});
    await assert.rejects(runSuite(page), /Refusing a browser context with unrelated pages/);
    assert.equal(calls.requests, 0);
    assert.equal(calls.navigations, 0);
  }
});

test("rejects a wrong health marker without interacting with the page", async () => {
  const {page, calls} = stubPage({marker: {fixture: "unrelated", synthetic: true}});
  await assert.rejects(runSuite(page), /not the expected synthetic test server/);
  assert.equal(calls.navigations, 0);
});

test("retains the original error when cleanup succeeds", async () => {
  const original = new Error("initial page failure");
  const {page, calls} = stubPage({gotoErrors: [original]});
  await assert.rejects(runSuite(page), error => {
    assert.match(error.message, /fixture setup.*initial page failure/);
    assert.equal(error.cause, original);
    return true;
  });
  assert.equal(calls.clearClicks, 1);
});

test("reports both original and cleanup errors without losing their causes", async () => {
  const original = new Error("initial page failure");
  const cleanup = new Error("cleanup page failure");
  const {page} = stubPage({gotoErrors: [original, cleanup]});
  await assert.rejects(runSuite(page), error => {
    assert.ok(error instanceof AggregateError);
    assert.equal(error.errors.length, 2);
    assert.equal(error.errors[0].cause, original);
    assert.equal(error.errors[1].cause, cleanup);
    assert.equal(error.cause, error.errors[0]);
    assert.match(error.message, /initial page failure.*cleanup page failure/);
    return true;
  });
});

test("missing identity produces a named failure without a default 30-second wait", async () => {
  const {page, calls} = stubPage({extraUrl: "about:blank"});
  await assert.rejects(runSuite(page), /Sign-in completes in the same tab and context.*Expected synthetic identity/);
  assert.equal(calls.identityReads, 0);
  assert.equal(calls.clearClicks, 2);
});
