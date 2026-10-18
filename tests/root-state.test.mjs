import { test } from "node:test";
import assert from "node:assert/strict";
import { migrateRootState } from "../report_viewer/state.mjs";
function browser(saved = {}, addressReport = null) {
  let values = {
    pins: [],
    seen: {},
    ...saved,
    selected: addressReport || saved.selected || "",
  };
  return {
    get values() {
      return values;
    },
    migrate(root, previous) {
      values = migrateRootState(
        { ...values, root: values.root ?? previous },
        root,
        Boolean(addressReport),
      );
    },
  };
}
test("legacy browser preserves local state exactly once", () => {
  const b = browser({
    pins: ["reports/old.html"],
    selected: "reports/old.html",
    seen: { "reports/old.html": 123 },
  });
  b.migrate("/workspace", "/workspace/Work");
  const migrated = JSON.parse(JSON.stringify(b.values));
  assert.deepEqual(migrated, {
    root: "/workspace",
    pins: ["Work/reports/old.html"],
    selected: "Work/reports/old.html",
    seen: { "Work/reports/old.html": 123 },
  });
  b.migrate("/workspace", "/workspace/Work");
  assert.deepEqual(JSON.parse(JSON.stringify(b.values)), migrated);
});
test("recorded root wins over the legacy hint on later expansion", () => {
  const b = browser({
    root: "/workspace/Work/project",
    pins: ["old.html"],
    selected: "old.html",
  });
  b.migrate("/workspace", "/workspace/Work");
  assert.equal(b.values.selected, "Work/project/old.html");
});
test("fresh browser keeps empty selection and root boundaries are respected", () => {
  const fresh = browser();
  fresh.migrate("/workspace", "/workspace/Work");
  assert.equal(fresh.values.selected, "");
  assert.equal(fresh.values.pins.length, 0);
  const other = browser({ root: "/workspace-other", selected: "other.html" });
  other.migrate("/workspace", "/workspace/Work");
  assert.equal(other.values.selected, "other.html");
});

test("report path supplied in the URL is already relative to the current root", () => {
  const path = "Work/project/reports/example.html";
  const b = browser({ selected: "old.html" }, path);
  b.migrate("/workspace", "/workspace/Work");
  assert.equal(b.values.selected, path);
});
