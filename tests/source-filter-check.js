async function check(page) {
  const origin = await page.evaluate(() => location.origin);
  const fail = (message) => {
    throw Error(message);
  };
  const sourcePaths = ["templates/login.html", "tests/golden/invoice.html"];
  await page.goto(origin + "/?days=0&type=");
  await page.locator("#list .report").first().waitFor();
  async function assertCatalog(sourceOnly) {
    const paths = await page.locator("#list .folder").allTextContents();
    if (!paths.length) fail("The catalog is empty");
    if (sourceOnly) {
      if (
        paths.length !== sourcePaths.length ||
        sourcePaths.some((path) => !paths.includes(path))
      ) {
        fail(
          "The source view does not contain both source files: " +
            JSON.stringify(paths),
        );
      }
    } else {
      if (sourcePaths.some((path) => paths.includes(path)))
        fail("A source file is in the default list");
      if (!paths.includes("example.html"))
        fail("The report is missing from the default list");
    }
  }
  await assertCatalog(false);
  await page
    .getByRole("combobox", { name: "Type", exact: true })
    .selectOption("Code and tests");
  await assertCatalog(true);
  const sourceUrl = page.url();
  if (
    (await page.evaluate(() =>
      new URL(location.href).searchParams.get("type"),
    )) !== "Code and tests"
  )
    fail("The source filter has no URL");
  await page.reload();
  await page.locator("#list .report").first().waitFor();
  await assertCatalog(true);
  // URL filters must override saved preferences in a different browser session.
  await page.evaluate(() =>
    localStorage.setItem("report-viewer:type-v2", JSON.stringify("HTML")),
  );
  await page.goto(sourceUrl);
  await page.locator("#list .report").first().waitFor();
  await assertCatalog(true);
  await page
    .getByRole("button", { name: /Portal template.*templates\/login.html/ })
    .click();
  await page
    .frameLocator("#frame")
    .getByRole("heading", { name: "Portal template", exact: true })
    .waitFor();
  await page.reload();
  await page
    .frameLocator("#frame")
    .getByRole("heading", { name: "Portal template", exact: true })
    .waitFor();
  await page
    .getByRole("button", { name: "Browse reports", exact: true })
    .click();
  await page
    .getByRole("combobox", { name: "Type", exact: true })
    .selectOption("");
  await assertCatalog(false);
  await page.reload();
  await page.locator("#list .report").first().waitFor();
  await assertCatalog(false);
  return {
    sourcesHiddenByDefault: true,
    sourcesAvailable: true,
    sourcePreview: true,
    refresh: true,
    filterLinks: true,
  };
}
