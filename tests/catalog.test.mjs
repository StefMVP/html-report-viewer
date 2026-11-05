import { test } from "node:test";
import assert from "node:assert/strict";
import { changedReport, matchesQuery } from "../report_viewer/catalog.mjs";

const row = {
  path: "Work/local-ai/reports/local-ai-report.html",
  title: "Overnight local-ai report",
  description: "Measured benchmarks",
  kind: "Report",
  modified: 100,
};

test("search matches a relative path, a full path and a home path", () => {
  for (const query of [
    "Work/local-ai/reports/local-ai-report.html",
    "/workspace/Work/local-ai/reports/local-ai-report.html",
    "~/Work/local-ai/reports/local-ai-report.html",
    "overnight LOCAL-AI",
    "measured benchmarks",
  ])
    assert.equal(matchesQuery(row, query, "/workspace"), true, query);
  for (const query of ["~/Work/other.html", "benchmark-missing", "/srv/report.html"])
    assert.equal(matchesQuery(row, query, "/workspace"), false, query);
});

test("search with no query keeps every report", () => {
  assert.equal(matchesQuery(row, "  ", "/workspace"), true);
  assert.equal(matchesQuery(row, "", ""), true);
});

test("a report with a new modification time asks for a reload", () => {
  const selected = { ...row };
  assert.equal(changedReport(selected, [row]), null);
  assert.equal(
    changedReport(selected, [{ ...row, modified: 200 }]).modified,
    200,
  );
  assert.equal(changedReport(null, [row]), null);
  assert.equal(changedReport(selected, []), null);
});
