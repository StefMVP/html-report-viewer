import { standaloneHTML } from "./export.mjs";
import { migrateRootState } from "./state.mjs";

const $ = (id) => document.getElementById(id);
const storage = {
  get(key, fallback) {
    try {
      return (
        JSON.parse(localStorage.getItem("report-viewer:" + key)) ?? fallback
      );
    } catch {
      return fallback;
    }
  },
  set(key, value) {
    try {
      localStorage.setItem("report-viewer:" + key, JSON.stringify(value));
    } catch {}
  },
};
const address = new URL(location.href),
  addressReport = address.searchParams.get("report");
for (const key of ["share", "collection"]) address.searchParams.delete(key);
history.replaceState(null, "", address);
let workspaceRoot = "",
  copyReset,
  rows = [],
  selected = null,
  busy = false,
  initialSelectionPending = Boolean(addressReport),
  previewLoad = 0,
  seen = storage.get("seen", {}),
  lastPath = addressReport || "";
const savedPins = storage.get("pins", []),
  pins = new Set(
    Array.isArray(savedPins)
      ? savedPins.filter(
          (path) => typeof path === "string" && !path.startsWith("share:"),
        )
      : [],
  );
const reportOrder = (a, b) =>
  Number(pins.has(b.path)) - Number(pins.has(a.path)) ||
  b.modified - a.modified ||
  a.path.localeCompare(b.path);
for (const id of ["days", "type"]) {
  const value =
    address.searchParams.get(id) ?? storage.get(id + "-v2", $(id).value);
  if ([...$(id).options].some((o) => o.value === value)) $(id).value = value;
}
function saveFilter(id) {
  storage.set(id + "-v2", $(id).value);
  const address = new URL(location.href);
  for (const filter of ["days", "type"])
    address.searchParams.set(filter, $(filter).value);
  history.replaceState(null, "", address);
}
function age(timestamp) {
  const seconds = Math.max(0, Date.now() / 1000 - timestamp);
  return seconds < 60
    ? "just now"
    : seconds < 3600
      ? Math.floor(seconds / 60) + "m ago"
      : seconds < 86400
        ? Math.floor(seconds / 3600) + "h ago"
        : Math.floor(seconds / 86400) + "d ago";
}
function render() {
  const query = $("search").value.trim().toLowerCase();
  const type = $("type").value;
  const cutoff =
    $("days").value === "0"
      ? 0
      : Date.now() / 1000 - Number($("days").value) * 86400;
  const filtered = rows
    .filter(
      (r) =>
        (pins.has(r.path) || r.path === lastPath || r.modified >= cutoff) &&
        (type ? (r.kind || "HTML") === type : r.kind !== "Code and tests") &&
        (r.title + " " + r.path + " " + r.description + " " + r.kind)
          .toLowerCase()
          .includes(query),
    )
    .sort(reportOrder);
  const scroll = $("list").scrollTop;
  const fragment = document.createDocumentFragment();
  for (const row of filtered) {
    const button = document.createElement("button");
    button.className =
      "report" + ((seen[row.path] || 0) < row.modified ? " unread" : "");
    button.setAttribute(
      "aria-current",
      String(selected && selected.path === row.path),
    );
    button.title =
      row.title +
      "\n" +
      row.path +
      "\nModified " +
      new Date(row.modified * 1000).toLocaleString() +
      (row.description ? "\n" + row.description : "");
    const title = document.createElement("span");
    title.className = "report-title";
    title.textContent = row.title;
    const meta = document.createElement("span");
    meta.className = "report-meta";
    const tag = document.createElement("span");
    tag.className = "type-tag";
    tag.dataset.kind = row.kind || "HTML";
    tag.textContent = tag.dataset.kind;
    tag.title = "Type inferred from report metadata, filename, and folder";
    const folder = document.createElement("span");
    folder.className = "folder";
    folder.textContent = row.path;
    const time = document.createElement("span");
    time.className = "age";
    time.textContent = age(row.modified);
    const item = document.createElement("div");
    item.className = "report-row";
    const pin = document.createElement("button");
    pin.className = "pin";
    pin.type = "button";
    pin.dataset.path = row.path;
    pin.title = (pins.has(row.path) ? "Unpin" : "Pin") + " report";
    pin.setAttribute("aria-label", pin.title + ": " + row.title);
    pin.setAttribute("aria-pressed", String(pins.has(row.path)));
    pin.innerHTML =
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 3h6l-1 7 4 4v2H6v-2l4-4-1-7Z"/><path d="M12 16v5"/></svg>';
    pin.onclick = () => {
      if (pins.has(row.path)) pins.delete(row.path);
      else pins.add(row.path);
      storage.set("pins", [...pins]);
      render();
      const replacement = [...$("list").querySelectorAll(".pin")].find(
        (el) => el.dataset.path === row.path,
      );
      (replacement || $("search")).focus({ preventScroll: true });
    };
    meta.append(tag, time);
    button.append(title, folder, meta);
    button.onclick = () => select(row);
    item.append(button, pin);
    fragment.append(item);
  }
  if (!filtered.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = rows.length
      ? "No matches. Try another search or type."
      : "No reports in this time window. Try a longer window.";
    fragment.append(empty);
  }
  $("list").replaceChildren(fragment);
  $("list").scrollTop = scroll;
}
const mobile = window.matchMedia("(max-width:650px)");
function setSidebar(open) {
  document.body.classList.toggle("collapsed", !open);
  $("toggle").setAttribute("aria-expanded", String(open));
}
function select(row) {
  initialSelectionPending = false;
  selected = { ...row };
  seen[row.path] = row.modified;
  lastPath = row.path;
  storage.set("selected", lastPath);
  storage.set("seen", seen);
  const address = new URL(location.href);
  address.searchParams.set("report", row.path);
  history.replaceState(null, "", address);
  // Replace the browsing context so each click starts a new document at the top.
  const frame = $("frame").cloneNode(false),
    url = new URL(row.url, previewOrigin);
  frame.setAttribute(
    "sandbox",
    "allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox",
  );
  url.searchParams.set("v", String(row.modified));
  url.searchParams.set("load", String(++previewLoad));
  frame.src = url.href;
  frame.hidden = false;
  $("frame").replaceWith(frame);
  $("welcome").hidden = true;
  $("current").textContent = row.path;
  $("current").title = row.path;
  $("open").dataset.url = previewOrigin + row.url;
  $("open").hidden = false;
  clearTimeout(copyReset);
  $("copy").hidden = false;
  $("copy").textContent = "Copy report";
  $("download").disabled = downloading;
  render();
  if (mobile.matches) {
    setSidebar(false);
    $("toggle").focus({ preventScroll: true });
  }
}
async function refresh() {
  if (busy) return;
  busy = true;
  try {
    // The health path supplies the local path for Copy; report discovery does not depend on it.
    if (!workspaceRoot) {
      try {
        const health = await fetch("/api/health", {
          signal: AbortSignal.timeout(10000),
        });
        if (health.ok) {
          const info = await health.json();
          {
            const state = migrateRootState(
              {
                root: storage.get("root", info.previousRoot),
                pins: [...pins],
                seen,
                selected: lastPath,
              },
              info.root,
              Boolean(addressReport),
            );
            pins.clear();
            for (const value of state.pins) pins.add(value);
            seen = state.seen;
            lastPath = state.selected;
            for (const key of ["root", "pins", "seen", "selected"])
              storage.set(key, state[key]);
          }
          workspaceRoot = info.root;
        }
      } catch {}
    }
    const fetchLocal = async (days) => {
      const params = new URLSearchParams({ days });
      for (const path of pins) params.append("pin", path);
      if (lastPath) params.append("pin", lastPath);
      const response = await fetch("/api/reports?" + params, {
        headers: { "X-Viewer-Token": viewerToken },
        cache: "no-store",
        signal: AbortSignal.timeout(60000),
      });
      if (!response.ok) throw Error("HTTP " + response.status);
      return (await response.json()).reports.sort(reportOrder);
    };
    rows = await fetchLocal($("days").value);
    // A short window with no reports should still open a useful catalog.
    if (!rows.length && $("days").value !== "0") {
      rows = await fetchLocal("30");
      if (rows.length) {
        $("days").value = "30";
        saveFilter("days");
      }
    }
    if (initialSelectionPending) {
      const initial = rows.find((r) => r.path === lastPath);
      if (initial) select(initial);
    }
    render();
    $("connection-error").hidden = true;
  } catch (error) {
    $("connection-error").hidden = false;
    $("connection-error").textContent =
      "Cannot refresh local reports. Retrying automatically.";
    render();
  } finally {
    busy = false;
  }
}
$("search").oninput = render;
$("type").onchange = () => {
  saveFilter("type");
  render();
};
for (const id of ["days"])
  $(id).onchange = () => {
    saveFilter(id);
    if (busy) {
      setTimeout(() => $(id).onchange(), 200);
      return;
    }
    refresh();
  };
$("copy").onclick = async () => {
  if (!selected || !workspaceRoot) return;
  const path = workspaceRoot + "/" + selected.path;
  const label = selected.title.replace(/[\\[\]]/g, "\\$&");
  const localLink =
    "[" +
    label +
    "](<" +
    path
      .replace(/%/g, "%25")
      .replace(/</g, "%3C")
      .replace(/>/g, "%3E")
      .replace(/\n/g, "%0A")
      .replace(/\r/g, "%0D") +
    ">)";
  try {
    await navigator.clipboard.writeText(localLink);
    $("copy").textContent = "Copied!";
  } catch {
    window.prompt("Copy this report link:", localLink);
  }
  clearTimeout(copyReset);
  copyReset = setTimeout(() => {
    $("copy").textContent = "Copy report";
  }, 1800);
};

let downloading = false;
$("download").onclick = async () => {
  if (!selected || downloading) return;
  const row = { ...selected },
    button = $("download");
  downloading = true;
  button.disabled = true;
  button.textContent = "Preparing…";
  try {
    const html = await standaloneHTML(row.url);
    const url = URL.createObjectURL(
      new Blob([html], { type: "text/html;charset=utf-8" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download =
      row.path
        .split("/")
        .pop()
        .replace(/\.html?$/i, "") + ".html";
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  } catch (error) {
    window.alert("Could not download standalone HTML. " + error.message);
  } finally {
    downloading = false;
    button.disabled = !selected;
    button.textContent = "Download report";
  }
};
function clearSelection() {
  selected = null;
  initialSelectionPending = false;
  const address = new URL(location.href);
  address.searchParams.delete("report");
  history.replaceState(null, "", address);
  const frame = $("frame").cloneNode(false);
  frame.hidden = true;
  frame.removeAttribute("src");
  $("frame").replaceWith(frame);
  $("welcome").hidden = false;
  $("current").textContent = "Select a report";
  $("copy").hidden = true;
  $("download").disabled = true;
  $("open").hidden = true;
}
function showList() {
  clearSelection();
  setSidebar(true);
  render();
  $("list").scrollTop = 0;
  document.querySelector(".toolbar").classList.remove("more-actions");
  $("more-actions").setAttribute("aria-expanded", "false");
}
$("open").onclick = () => {
  if (selected) window.open($("open").dataset.url, "_blank", "noopener");
};
$("toggle").onclick = showList;
$("more-actions").onclick = () => {
  $("more-actions").setAttribute(
    "aria-expanded",
    String(document.querySelector(".toolbar").classList.toggle("more-actions")),
  );
};
mobile.addEventListener("change", () =>
  setSidebar(!mobile.matches || !selected),
);
setSidebar(true);
refresh();
setInterval(refresh, 15000);
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) refresh();
});
