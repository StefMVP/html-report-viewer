# Running the viewer

For requests to run report viewer or http://localhost:8766/, use
`./scripts/report-viewer-service start`. On first setup, pass `--root` with the
desired report discovery folder. This runs headlessly under the systemd user
manager and persists independently of the terminal or chat session.

Use the launcher's `status` and `logs` commands to inspect it, and `restart`
after changing application code.
