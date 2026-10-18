async function check(page) {
  const origin = await page.evaluate(() => location.origin);
  const context = page.context();
  const fail = (message) => {
    throw Error(message);
  };
  // Internet sites usually refuse frames, so this stand-in refuses them too.
  await context.route("https://external.example/**", (route) =>
    route.fulfill({
      contentType: "text/html",
      headers: { "X-Frame-Options": "DENY" },
      body: "<title>External page</title><h1>External page</h1>",
    }),
  );
  const preview = () => page.mainFrame().childFrames()[0];
  async function openReport() {
    await page.goto(origin + "/?days=0&report=links.html");
    await page
      .frameLocator("#frame")
      .getByRole("heading", { name: "Link report", exact: true })
      .waitFor();
  }
  async function newTab(id) {
    const opening = context.waitForEvent("page", { timeout: 5000 });
    await page.frameLocator("#frame").locator("#" + id).click();
    const tab = await opening.catch(() =>
      fail(id + " opened no tab; the preview shows " + preview().url()),
    );
    await tab.getByRole("heading", { name: "External page" }).waitFor();
    const url = tab.url();
    await tab.close();
    return url;
  }
  const result = {};

  // Reports link files by preview URL, by absolute path and by file URL.
  for (const id of ["local", "path", "file"]) {
    await openReport();
    await page.frameLocator("#frame").locator("#" + id).click();
    await page
      .frameLocator("#frame")
      .getByRole("heading", { name: "Older report", exact: true })
      .waitFor({ timeout: 5000 })
      .catch(() => fail("The " + id + " link shows " + preview().url()));
    result[id] = preview().url().replace(/^[a-z]+:\/\/[^/]+/, "").split("?")[0];
  }

  await openReport();
  result.internet = await newTab("internet");
  if (result.internet !== "https://external.example/page?from=report")
    fail("The internet link opened " + result.internet);
  if (!preview().url().includes("/files/links.html"))
    fail("The internet link replaced the report: " + preview().url());

  result.newTab = await newTab("new-tab");

  const pages = context.pages().length;
  await page.frameLocator("#frame").locator("#section").click();
  await page.waitForTimeout(300);
  if (context.pages().length !== pages || !preview().url().endsWith("#end"))
    fail("The section link left the report: " + preview().url());
  return result;
}
