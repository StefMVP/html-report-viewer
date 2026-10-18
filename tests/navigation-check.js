async function check(page) {
  const origin = page.url().split("/").slice(0, 3).join("/");
  const fail = (message) => {
    throw Error(message);
  };
  const reportRequests = [];
  page.on("request", (request) => {
    if (request.url().includes("/files/")) reportRequests.push(request.url());
  });
  await page.evaluate(() => {
    localStorage.setItem(
      "report-viewer:selected",
      JSON.stringify("example.html"),
    );
    localStorage.setItem(
      "report-viewer:selected-shared",
      JSON.stringify("old-share"),
    );
    localStorage.setItem("report-viewer:tab", JSON.stringify("shared"));
    localStorage.setItem("report-viewer:pins", JSON.stringify(["older.html"]));
  });
  async function assertList() {
    await page.locator("#list .report").first().waitFor();
    const state = await page.evaluate(() => ({
      selected: document.querySelector(".report[aria-current=true]") !== null,
      hidden: document.querySelector("#frame").hidden,
      source: document.querySelector("#frame").getAttribute("src"),
      scroll: document.querySelector("#list").scrollTop,
      collapsed: document.body.classList.contains("collapsed"),
      query:
        new URL(location.href).searchParams.has("report") ||
        new URL(location.href).searchParams.has("share"),
    }));
    if (
      state.selected ||
      !state.hidden ||
      state.source ||
      state.scroll ||
      state.collapsed ||
      state.query
    )
      fail("Expected the report list: " + JSON.stringify(state));
  }
  for (const width of [390, 1280]) {
    await page.setViewportSize({ width, height: 844 });
    await page.goto(origin + "/");
    await assertList();
    if (
      await page
        .locator("[role=tab],#share,#unshare,#update-share,#public-current")
        .count()
    )
      fail("Sharing controls remain");
    if (
      !(await page.locator("#list .report").first().innerText()).includes(
        "Older report",
      )
    )
      fail("The pinned report is missing from the top");
    if (
      !(await page.locator("#list .report").nth(1).innerText()).includes(
        "Example report",
      )
    )
      fail("The newest unpinned report is missing");
    if (
      !(await page.locator("#list .report").nth(2).innerText()).includes(
        "Recent report",
      )
    )
      fail("Unpinned reports are not in date order");
    if (reportRequests.length) fail("A report loaded before a click");
  }
  // Repeat clicks on one row must create a new document, even with unchanged catalog metadata.
  for (const width of [390, 1280]) {
    await page.setViewportSize({ width, height: 844 });
    for (let attempt = 0; attempt < 3; attempt++) {
      await page
        .locator(".report")
        .filter({ hasText: "Example report" })
        .click();
      await page
        .frameLocator("#frame")
        .getByRole("heading", { name: "Example report", exact: true })
        .waitFor();
      const frame = page
        .frames()
        .find((frame) => frame.url().includes("/files/example.html"));
      if (await frame.evaluate(() => window.navigationCheck))
        fail("The previous report document was reused");
      if ((await frame.evaluate(() => scrollY)) !== 0)
        fail("The report did not open at the top");
      await frame.evaluate(() => {
        window.navigationCheck = true;
        window.scrollTo(0, 99999);
      });
      await page.evaluate(() => {
        document.querySelector("#list").scrollTop = 99999;
      });
      await page.locator("#toggle").click();
      await assertList();
    }
  }
  // Open a row below the fold, then return to the top of the catalog.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator("#list").evaluate((list) => {
    list.scrollTop = list.scrollHeight;
  });
  if ((await page.locator("#list").evaluate((list) => list.scrollTop)) <= 0)
    fail("The catalog fixture does not scroll");
  await page.locator("#list .report").last().click();
  await page
    .frameLocator("#frame")
    .getByRole("heading", { name: "Catalog report 8", exact: true })
    .waitFor();
  await page.locator("#toggle").click();
  await assertList();
  // A click selects only its row; refresh and direct links must keep that row.
  await page.locator(".report").filter({ hasText: "Older report" }).click();
  await page
    .frameLocator("#frame")
    .getByRole("heading", { name: "Older report", exact: true })
    .waitFor();
  const deepLink = page.url();
  await page.reload();
  await page
    .frameLocator("#frame")
    .getByRole("heading", { name: "Older report", exact: true })
    .waitFor();
  await page.goto(origin + "/");
  await assertList();
  // A failed first catalog request must allow the requested report to open on retry.
  let firstRequest = true;
  await page.route("**/api/reports?*", async (route) => {
    if (firstRequest) {
      firstRequest = false;
      await route.fulfill({ status: 503, body: "Unavailable" });
    } else await route.continue();
  });
  await page.goto(deepLink);
  await page.locator("#connection-error:not([hidden])").waitFor();
  await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
  await page
    .frameLocator("#frame")
    .getByRole("heading", { name: "Older report", exact: true })
    .waitFor();
  await page.unroute("**/api/reports?*");
  await page.locator("#toggle").click();
  await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
  await assertList();
  // Rapid clicks must finish at the last selected document.
  await page.evaluate(() => {
    const reports = [...document.querySelectorAll("#list .report")];
    reports.find((row) => row.textContent.includes("Example report")).click();
    reports.find((row) => row.textContent.includes("Older report")).click();
  });
  await page
    .frameLocator("#frame")
    .getByRole("heading", { name: "Older report", exact: true })
    .waitFor();
  return {
    rootList: true,
    pinnedFirst: true,
    newestUnpinnedFirst: true,
    freshDocument: true,
    topOnReturn: true,
    deepLink: true,
    retry: true,
    rapidClicks: true,
    widths: [390, 1280],
  };
}
