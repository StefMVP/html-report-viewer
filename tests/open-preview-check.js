async function check(page) {
  await page.setViewportSize({ width: 1280, height: 900 });
  const origin = await page.evaluate(() => location.origin);
  await page.goto(origin + "/");
  await page.locator("#search").fill("Example report");
  await page.locator(".report").filter({ hasText: "Example report" }).click();
  await page
    .frameLocator("#frame")
    .getByRole("heading", { name: "Example report", exact: true })
    .waitFor();
  const preview = await page.locator("#open").getAttribute("data-url");
  const opening = page.context().waitForEvent("page");
  await page.locator("#open").click();
  const opened = await opening;
  await opened
    .getByRole("heading", { name: "Example report", exact: true })
    .waitFor();
  await opened.close();
  await page.evaluate((url) => {
    const link = document.createElement("a");
    link.id = "test-direct-open";
    link.href = url;
    link.target = "_blank";
    link.rel = "noreferrer";
    link.textContent = "Open without a referrer";
    document.body.append(link);
  }, preview);
  const directOpening = page.context().waitForEvent("page");
  await page.locator("#test-direct-open").click();
  const direct = await directOpening;
  await direct
    .getByRole("heading", { name: "Example report", exact: true })
    .waitFor();
  await direct.screenshot({
    path: "screenshots/preview-direct-open.png",
    fullPage: true,
  });
  await direct.close();
  await page.locator("#test-direct-open").evaluate((link) => link.remove());
  await page.screenshot({
    path: "screenshots/preview-open-viewer.png",
    fullPage: true,
  });
  return { openButton: true, withoutReferrer: true, preview };
}
