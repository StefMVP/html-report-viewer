async function check(page) {
  const origin = page.url().split("/").slice(0, 3).join("/");
  await page.goto(origin + "/?days=0&type=Report&report=export%2Findex.html");
  await page
    .frameLocator("#frame")
    .getByRole("heading", { name: "Asset export report", exact: true })
    .waitFor();
  await page
    .frameLocator("#frame")
    .frameLocator("#nested")
    .getByRole("heading")
    .waitFor();
  const saved = page.waitForEvent("download");
  await page.locator("#download").click();
  const download = await saved;
  await download.saveAs(".runtime/export-download.html");
  const file = (await download.path()) + ".html";
  await download.saveAs(file);
  const offline = await page.context().browser().newContext();
  const escapedRequests = [];
  await offline.route(/^https?:/, (route) => {
    escapedRequests.push(route.request().url());
    return route.abort();
  });
  const result = await offline.newPage();
  const errors = [];
  result.on("pageerror", (error) => errors.push(error.message));
  result.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  try {
    await result.goto("file://" + file);
    await result
      .locator("#module-result")
      .filter({ hasText: "blue AB JSON dynamic" })
      .waitFor({ timeout: 5000 });
    if ((await result.locator("#inline-result").textContent()) !== "blue")
      throw Error("Inline module failed");
    if (
      (await result
        .locator("#styled")
        .evaluate((el) => getComputedStyle(el).color)) !== "rgb(10, 20, 30)"
    )
      throw Error("External stylesheet failed");
    const image = await result.locator("#image").evaluate(async (el) => {
      await el.decode();
      return {
        width: el.naturalWidth,
        height: el.naturalHeight,
        src: el.currentSrc.slice(0, 60),
      };
    });
    if (image.width <= 0 || !image.src.startsWith("data:"))
      throw Error("Image or srcset failed: " + JSON.stringify(image));
    await result.locator("#audio").evaluate((el) => el.load());
    await result.waitForFunction(
      () => Number.isFinite(document.querySelector("#audio").duration),
      null,
      { timeout: 5000 },
    );
    await result.locator("#classic").click();
    if (
      (await result.locator("#classic").textContent()) !==
      "Classic script works"
    )
      throw Error("Classic script failed");
    await result.locator("#classic-import").click();
    await result
      .locator("#classic-import")
      .filter({ hasText: "dynamic" })
      .waitFor({ timeout: 5000 });
    for (const id of ["nested", "inline-frame"]) {
      const frame = result.frameLocator("#" + id);
      await frame.getByRole("heading").waitFor();
      if (
        !(await frame.locator("img").evaluate(async (el) => {
          await el.decode();
          return el.naturalWidth === 16;
        }))
      )
        throw Error("Nested image failed: " + id);
      if (
        (await frame
          .locator("h2")
          .evaluate((el) => getComputedStyle(el).color)) !== "rgb(30, 40, 50)"
      )
        throw Error("Nested stylesheet failed: " + id);
    }
    if (
      (await result
        .frameLocator("#inline-frame")
        .locator("body")
        .getAttribute("data-theme")) !== "blue"
    )
      throw Error("srcdoc module failed");
    if (escapedRequests.length)
      throw Error("Offline export requested " + escapedRequests.join(", "));
    return {
      offline: true,
      externalCSS: true,
      images: true,
      audio: true,
      classicScripts: true,
      moduleGraph: true,
      cycles: true,
      dynamicImport: true,
      JSONModule: true,
      importMap: true,
      srcdoc: true,
      nestedFrames: true,
    };
  } catch (error) {
    throw Error(
      error.message +
        "; Body: " +
        (await result.locator("body").innerText()).slice(0, 250) +
        "; Audio: " +
        JSON.stringify(
          await result
            .locator("#audio")
            .evaluate((el) => ({
              ready: el.readyState,
              network: el.networkState,
              duration: el.duration,
              error: el.error?.message,
              src: el.currentSrc.slice(0, 80),
            })),
        ) +
        "; Browser errors: " +
        errors.join(" | "),
    );
  } finally {
    await offline.close();
  }
}
