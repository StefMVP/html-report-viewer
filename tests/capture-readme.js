async function capture(page) {
  const origin = page.url().split("/").slice(0, 3).join("/");
  await page.setViewportSize({ width: 1360, height: 940 });
  await page.goto(origin + "/");
  const data = await page.evaluate(async () => {
    const health = await (await fetch("/api/health")).json();
    if (health.version !== "test")
      throw Error("Use the temporary demo fixture");
    const response = await fetch("/api/reports?days=7", {
      headers: { "X-Viewer-Token": viewerToken },
    });
    if (!response.ok) throw Error("The demo catalog could not be read");
    return response.json();
  });
  const sorted = data.reports.sort((a, b) => b.modified - a.modified);
  const expectedFirst = "Task board · drag and drop verification";
  if (sorted.length !== 9 || sorted[0].title !== expectedFirst)
    throw Error("Start tests/browser_fixture.py with --demo before capture");
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  const rows = page.locator("#list .report");
  await rows.nth(8).waitFor();
  const titles = await rows.locator(".report-title").allTextContents();
  if (titles.length !== 9 || titles[0] !== expectedFirst)
    throw Error("Start tests/browser_fixture.py with --demo before capture");
  if (titles.some((title) => /Example report|Catalog report/.test(title)))
    throw Error("The catalog still contains generic test reports");
  await rows.first().click();
  const report = page.frameLocator("#frame");
  await report
    .getByRole("heading", { name: "Moving tasks keeps their state" })
    .waitFor();
  await report.getByText("Fictional demo", { exact: true }).waitFor();
  if ((await report.locator(".task").count()) !== 6)
    throw Error("The task-board mockup is not populated");
  if (JSON.stringify(sorted.map((row) => row.title)) !== JSON.stringify(titles))
    throw Error("The catalog is not in newest-first order");
  await page.screenshot({ path: "docs/viewer.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: "screenshots/demo-mobile.png",
    fullPage: true,
  });
  return {
    screenshot: "docs/viewer.png",
    fictionalReports: titles,
    populatedTasks: 6,
  };
}
