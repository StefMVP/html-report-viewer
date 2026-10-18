export function migrateRootState(saved, root, explicitSelection = false) {
  const state = {
    ...saved,
    root,
    pins: [...saved.pins],
    seen: { ...saved.seen },
  };
  if (
    saved.root &&
    saved.root !== root &&
    saved.root.startsWith(root.replace(/\/$/, "") + "/")
  ) {
    const prefix = saved.root.slice(root.replace(/\/$/, "").length + 1) + "/";
    const migrate = (path) => (path ? prefix + path : path);
    state.pins = state.pins.map(migrate);
    state.seen = Object.fromEntries(
      Object.entries(state.seen).map(([path, value]) => [migrate(path), value]),
    );
    if (!explicitSelection) state.selected = migrate(state.selected);
  }
  return state;
}
