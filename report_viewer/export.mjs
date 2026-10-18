import { parse } from "./vendor/es-module-lexer.mjs";

export async function standaloneHTML(url) {
  const cache = new Map();
  const absolute = (value, base) => new URL(value, base).href;
  const embedded = (value) => !value || /^(data:|#|about:)/i.test(value.trim());
  async function read(url) {
    const response = await fetch(url, {
      cache: "no-store",
      signal: AbortSignal.timeout(30000),
    });
    if (!response.ok)
      throw Error("Cannot embed " + url + " (HTTP " + response.status + ")");
    return response;
  }
  function dataURL(blob) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(blob);
    });
  }
  async function asset(value, base) {
    if (embedded(value)) return value;
    const url = new URL(value, base),
      hash = url.hash;
    url.hash = "";
    if (!cache.has(url.href))
      cache.set(
        url.href,
        read(url.href)
          .then((r) => r.blob())
          .then(dataURL),
      );
    return (await cache.get(url.href)) + hash;
  }
  async function replaceAsync(value, pattern, replace) {
    const matches = [...value.matchAll(pattern)],
      values = await Promise.all(matches.map(replace));
    let index = 0;
    return value.replace(pattern, () => values[index++]);
  }
  async function css(value, base, parents = []) {
    // Imported CSS keeps its media/layer conditions; its own URLs use its source directory.
    value = await replaceAsync(
      value,
      /@import\s+(?:url\(\s*(?:"([^"]*)"|'([^']*)'|([^\s)]*))\s*\)|"([^"]*)"|'([^']*)')/gi,
      async (match) => {
        const ref = match.slice(1).find((v) => v !== undefined);
        if (embedded(ref)) return match[0];
        const url = absolute(ref, base);
        if (parents.includes(url))
          throw Error("Circular stylesheet import: " + url);
        const content = await css(await (await read(url)).text(), url, [
          ...parents,
          url,
        ]);
        return (
          '@import url("' +
          (await dataURL(new Blob([content], { type: "text/css" }))) +
          '")'
        );
      },
    );
    return replaceAsync(
      value,
      /url\(\s*(?:"([^"]*)"|'([^']*)'|([^\s)]*))\s*\)/gi,
      async (match) =>
        'url("' +
        (await asset(
          match.slice(1).find((v) => v !== undefined),
          base,
        )) +
        '")',
    );
  }
  async function embedModules(doc, base) {
    const imports = {},
      scopes = {};
    const normalize = (value) =>
      /^(?:[./]|[a-z][a-z0-9+.-]*:)/i.test(value)
        ? absolute(value, base)
        : value;
    const mappings = (entries) =>
      Object.fromEntries(
        Object.entries(entries || {}).map(([key, value]) => [
          normalize(key),
          value === null ? null : absolute(value, base),
        ]),
      );
    for (const script of doc.querySelectorAll('script[type="importmap"]')) {
      const map = JSON.parse(script.textContent);
      Object.assign(imports, mappings(map.imports));
      for (const [scope, values] of Object.entries(map.scopes || {}))
        scopes[absolute(scope, base)] = {
          ...scopes[absolute(scope, base)],
          ...mappings(values),
        };
      script.remove();
    }
    function match(specifier, values) {
      const key = Object.keys(values)
        .filter(
          (key) =>
            key === specifier ||
            (key.endsWith("/") && specifier.startsWith(key)),
        )
        .sort((a, b) => b.length - a.length)[0];
      if (key === undefined) return;
      if (values[key] === null)
        throw Error("Blocked module import: " + specifier);
      return values[key] + specifier.slice(key.length);
    }
    function resolve(specifier, importer) {
      const normalized = /^(?:[./]|[a-z][a-z0-9+.-]*:)/i.test(specifier)
        ? absolute(specifier, importer)
        : specifier;
      for (const scope of Object.keys(scopes).sort(
        (a, b) => b.length - a.length,
      )) {
        if (importer.startsWith(scope)) {
          const resolved = match(normalized, scopes[scope]);
          if (resolved !== undefined) return resolved;
        }
      }
      const resolved = match(normalized, imports);
      if (resolved !== undefined) return resolved;
      if (!/^[a-z][a-z0-9+.-]*:/i.test(normalized))
        throw Error("Unmapped module import: " + specifier);
      return normalized;
    }
    const modules = new Map();
    async function module(url, inline, inlineBase = url) {
      if (modules.has(url)) return modules.get(url).id;
      const record = {
        id: "https://report-viewer.invalid/module/" + modules.size,
      };
      modules.set(url, record);
      const response = inline === undefined ? await read(url) : null;
      let source = inline ?? (await response.text());
      const sourceBase = response?.url || inlineBase;
      if (response?.headers.get("content-type")?.includes("application/json")) {
        record.data = await dataURL(
          new Blob([source], { type: "application/json" }),
        );
        return record.id;
      }
      const edits = [];
      for (const item of parse(source)[0]) {
        if (item.d === -2) {
          const property = source.slice(item.e).match(/^\s*\.\s*url\b/);
          if (property)
            edits.push([
              item.s,
              item.e + property[0].length,
              JSON.stringify(sourceBase),
            ]);
        } else if (item.n !== undefined) {
          const id = await module(resolve(item.n, sourceBase));
          edits.push([item.s, item.e, item.d === -1 ? id : JSON.stringify(id)]);
        }
      }
      for (const [start, end, value] of edits.sort((a, b) => b[0] - a[0]))
        source = source.slice(0, start) + value + source.slice(end);
      record.source = source;
      record.data = await dataURL(
        new Blob([source], { type: "text/javascript" }),
      );
      return record.id;
    }
    const roots = [];
    for (const script of doc.querySelectorAll("script")) {
      if (
        !["", "module", "text/javascript", "application/javascript"].includes(
          script.type,
        )
      )
        continue;
      if (
        !script.hasAttribute("src") &&
        script.type !== "module" &&
        !parse(script.textContent)[0].length
      )
        continue;
      const url = script.hasAttribute("src")
        ? absolute(script.getAttribute("src"), base)
        : base + "#export-inline-" + roots.length;
      roots.push([
        script,
        await module(
          url,
          script.hasAttribute("src") ? undefined : script.textContent,
          base,
        ),
      ]);
    }
    if (!roots.length) return;
    const bundled = Object.fromEntries(
      [...modules.values()].map((record) => [record.id, record.data]),
    );
    const map = doc.createElement("script");
    map.type = "importmap";
    map.textContent = JSON.stringify({ imports: bundled }).replace(
      /</g,
      "\\u003c",
    );
    doc.head.prepend(map);
    for (const [script, id] of roots) {
      if (script.type === "module" || script.hasAttribute("src")) {
        script.src = bundled[id];
        script.textContent = "";
      } else {
        script.textContent = [...modules.values()].find(
          (record) => record.id === id,
        ).source;
      }
      script.removeAttribute("integrity");
      script.removeAttribute("crossorigin");
    }
  }
  async function documentHTML(url, parents = []) {
    if (parents.includes(url))
      throw Error("Circular embedded document: " + url);
    const response = await read(url);
    return transformHTML(await response.text(), response.url, [
      ...parents,
      url,
    ]);
  }
  async function transformHTML(html, inheritedBase, parents = []) {
    const doc = new DOMParser().parseFromString(html, "text/html");
    const base = absolute(
      doc.querySelector("base[href]")?.getAttribute("href") || inheritedBase,
      inheritedBase,
    );
    // A source CSP may disallow the data URLs required by an offline export.
    doc
      .querySelectorAll('base,meta[http-equiv="Content-Security-Policy" i]')
      .forEach((el) => el.remove());
    doc
      .querySelectorAll('meta[charset],meta[http-equiv="Content-Type" i]')
      .forEach((el) => el.remove());
    const charset = doc.createElement("meta");
    charset.setAttribute("charset", "utf-8");
    doc.head.prepend(charset);
    for (const link of doc.querySelectorAll("link[href]")) {
      if (link.relList.contains("stylesheet")) {
        const source = absolute(link.getAttribute("href"), base);
        link.href = await dataURL(
          new Blob(
            [await css(await (await read(source)).text(), source, [source])],
            { type: "text/css" },
          ),
        );
        link.removeAttribute("integrity");
        link.removeAttribute("crossorigin");
      } else if (link.relList.contains("icon"))
        link.href = await asset(link.getAttribute("href"), base);
      else link.remove();
    }
    for (const style of doc.querySelectorAll("style"))
      style.textContent = await css(style.textContent, base);
    for (const el of doc.querySelectorAll("[style]"))
      el.setAttribute("style", await css(el.getAttribute("style"), base));
    await embedModules(doc, base);
    for (const el of doc.querySelectorAll(
      'script[src]:not([type=module]),img[src],input[type="image"][src],audio[src],video[src],source[src],track[src],embed[src],video[poster],object[data],image[href],image[xlink\\:href]',
    )) {
      for (const attr of ["src", "poster", "data", "href", "xlink:href"])
        if (el.hasAttribute(attr))
          el.setAttribute(attr, await asset(el.getAttribute(attr), base));
      el.removeAttribute("integrity");
      el.removeAttribute("crossorigin");
    }
    for (const el of doc.querySelectorAll("[srcset]")) {
      el.setAttribute(
        "srcset",
        await replaceAsync(
          el.getAttribute("srcset"),
          /(data:[^\s]+|[^\s,]+)(\s+[^,]+)?(?:,\s*|$)/g,
          async (match) => {
            const ref = match[1].replace(/,+$/, "");
            return (await asset(ref, base)) + (match[2] || "") + ", ";
          },
        ),
      );
    }
    for (const frame of doc.querySelectorAll("iframe[srcdoc]")) {
      frame.setAttribute(
        "srcdoc",
        await transformHTML(frame.getAttribute("srcdoc"), base, parents),
      );
      frame.removeAttribute("src");
    }
    for (const frame of doc.querySelectorAll("iframe[src]:not([srcdoc])")) {
      const ref = frame.getAttribute("src");
      if (!embedded(ref)) {
        frame.setAttribute(
          "srcdoc",
          await documentHTML(absolute(ref, base), parents),
        );
        frame.removeAttribute("src");
      }
    }
    // Preserve navigation without making display assets depend on the viewer.
    for (const el of doc.querySelectorAll("a[href],form[action]")) {
      const attr = el.tagName === "A" ? "href" : "action",
        value = el.getAttribute(attr);
      if (!embedded(value)) el.setAttribute(attr, absolute(value, base));
    }
    return "<!doctype html>\n" + doc.documentElement.outerHTML;
  }
  return documentHTML(absolute(url, location.href));
}
