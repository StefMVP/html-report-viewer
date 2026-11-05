async function check(page) {
  const origin = page.url().split("/").slice(0, 3).join("/");
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto(origin + "/?days=0");
  // Search accepts the path a caller has on disk, including a home prefix.
  await page.locator("#search").fill("~/recent.html");
  await page
    .locator("#list .report")
    .filter({ hasText: "Recent report" })
    .waitFor();
  if ((await page.locator("#list .report").count()) !== 1)
    throw Error("Search did not narrow to the requested path");
  await page.locator("#list .report").first().click();
  await page
    .frameLocator("#frame")
    .getByRole("heading", { name: "Recent report", exact: true })
    .waitFor();
  const source = () =>
    page.evaluate(() => document.querySelector("#frame").getAttribute("src"));
  const before = await source();
  // The catalog reports a newer file for the open report.
  await page.route("**/api/reports?*", async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    for (const report of body.reports)
      if (report.path === "recent.html") report.modified += 120;
    await route.fulfill({ response, json: body });
  });
  await page.evaluate(() =>
    document.dispatchEvent(new Event("visibilitychange")),
  );
  await page.waitForFunction(
    (previous) => document.querySelector("#frame").getAttribute("src") !== previous,
    before,
  );
  await page.unroute("**/api/reports?*");
  const after = await source();
  if (!after.includes("v=") || !after.includes("recent.html"))
    throw Error("The open report did not reload from its file");
  await page
    .frameLocator("#frame")
    .getByRole("heading", { name: "Recent report", exact: true })
    .waitFor();
  return { searchByPath: true, reloadOnChange: true, before, after };
}
