async function check(page) {
  const origin = page.url().split("/").slice(0, 3).join("/");
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto(origin + "/");
  const requests = [];
  page.on("request", (request) => requests.push(request.url()));
  await page
    .context()
    .grantPermissions(["clipboard-read", "clipboard-write"], { origin });
  await page.locator("#days").selectOption("7");
  await page.locator("#search").fill("Example report");
  await page.locator(".report").filter({ hasText: "Example report" }).click();
  await page
    .frameLocator("#frame")
    .getByRole("heading", { name: "Example report", exact: true })
    .waitFor();
  const preview = page
    .frames()
    .find((frame) => frame.url().includes("/files/example.html"));
  const isolation = await preview.evaluate(async () => {
    let parentBlocked = false;
    try {
      parent.document.body.innerText;
    } catch {
      parentBlocked = true;
    }
    return {
      parentBlocked,
      localFetch: (await fetch(location.pathname)).status,
    };
  });
  if (!isolation.parentBlocked || isolation.localFetch !== 200)
    throw Error("Local preview isolation or live reads failed");
  if (
    await page
      .locator("[role=tab],#share,#unshare,#update-share,#public-current")
      .count()
  )
    throw Error("Sharing controls remain");
  for (const id of ["copy", "download", "open"])
    if (!(await page.locator("#" + id).isVisible()))
      throw Error("Missing local control " + id);
  await page.locator("#copy").click();
  const copied = await page.evaluate(() => navigator.clipboard.readText());
  if (
    !copied.startsWith("[Example report](<") ||
    !copied.includes("example.html")
  )
    throw Error("Copy report did not copy a local file link");
  const downloadEvent = page.waitForEvent("download");
  await page.locator("#download").click();
  const download = await downloadEvent;
  await download.saveAs(".runtime/test-local-download.html");
  if (download.suggestedFilename() !== "example.html")
    throw Error("Bad download filename");
  await page
    .frameLocator("#frame")
    .getByRole("button", { name: "Enlarge" })
    .click();
  await page.frameLocator("#frame").locator("dialog[open]").waitFor();
  await page
    .frameLocator("#frame")
    .getByRole("button", { name: "Close", exact: true })
    .click();
  if (requests.some((url) => url.includes("/api/share")))
    throw Error("The viewer requested the sharing API");
  await page.screenshot({
    path: "screenshots/local-viewer-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator("#toggle").click();
  await page.locator(".report").filter({ hasText: "Example report" }).click();
  await page.locator("#more-actions").click();
  if (
    !(await page.locator("#copy").isVisible()) ||
    !(await page.locator("#download").isVisible())
  )
    throw Error("Mobile local actions are missing");
  if (!(await page.locator("aside").isHidden()))
    throw Error("Mobile report list did not close");
  await page.screenshot({
    path: "screenshots/local-viewer-mobile.png",
    fullPage: true,
  });
  return {
    isolation,
    localCopy: true,
    download: download.suggestedFilename(),
    interactivePreview: true,
    noSharingControls: true,
    noSharingRequests: true,
    widths: [390, 1280],
  };
}
