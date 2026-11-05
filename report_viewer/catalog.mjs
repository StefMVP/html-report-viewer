export function matchesQuery(row, query, root) {
  const term = query.trim().toLowerCase();
  if (!term) return true;
  const absolute = root ? root.replace(/\/$/, "") + "/" + row.path : "";
  return [row.title, row.path, row.description, row.kind, absolute]
    .join(" ")
    .toLowerCase()
    .includes(term.replace(/^~\//, ""));
}

export function changedReport(selected, rows) {
  if (!selected) return null;
  const current = rows.find((row) => row.path === selected.path);
  return current && current.modified !== selected.modified ? current : null;
}
