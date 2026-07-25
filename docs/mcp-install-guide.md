# MCP Install Guide

External MCP servers used in this project's Claude Code workflow.
These are **user-scope** installs (not committed to `.mcp.json`).

---

## 1. spectrafit-reports (project-scope, built-in)

Already registered in `.mcp.json`. Exposes benchmark run artifacts as four tools:
`list_runs`, `latest_results`, `load_manifest`, `find_report_html`.

No install needed — runs via `uv run --with mcp python scripts/mcp_spectrafit_reports.py`.

---

## 2. Memory MCP (`@modelcontextprotocol/server-memory`)

### Install

```bash
claude mcp add memory -s user -- npx -y @modelcontextprotocol/server-memory
```

### Use case

Persistent key-value memory across Claude Code sessions. During spectrafit
development this is used to carry V&V cycle history — triage resolutions
(confirmed bugs, refuted non-bugs, design-debt items), benchmark gate results,
and ADR decisions — so a new session can read `memory:list` and resume context
without re-running the bench or re-reading DECISIONS.md. The server stores
entries in a local JSON file under `~/.config/mcp-server-memory/` and exposes
them as `memory:read`, `memory:write`, `memory:list`, `memory:delete` tool
calls. Write after every significant finding; read at session start.

### Verify

```bash
claude mcp list
# should show: memory   ✓ connected   (user scope)
```

---

## 3. GitLab MCP (`@zereight/mcp-gitlab` against `gitlab.gwdg.de`)

### Install

```bash
claude mcp add gitlab -s user \
  -e GITLAB_PERSONAL_ACCESS_TOKEN=<your-PAT> \
  -e GITLAB_API_URL=https://gitlab.gwdg.de/api/v4 \
  -- npx -y @zereight/mcp-gitlab
```

Replace `<your-PAT>` with a GitLab PAT that has `read_api` + `read_repository`
scopes (add `write_repository` if you need MR creation). The PAT is stored in
the user-scope MCP env, never committed.

### What the PAT needs

| Scope | Required for |
|---|---|
| `read_api` | Issue/MR search, pipeline status |
| `read_repository` | File contents, commit history |
| `write_repository` | Creating / updating MRs (optional) |

### Use case

Browse `gitlab.gwdg.de` CI pipelines, issues, and MRs from within Claude Code
without opening a browser. During spectrafit development: checking if a Kaniko
or coverage job failed, reading upstream rust/pyo3 issues, and cross-referencing
CI artefacts against local benchmark regressions. The MCP exposes tools like
`gitlab_list_pipelines`, `gitlab_get_file`, `gitlab_list_issues`,
`gitlab_search_code`.

### Verify

```bash
claude mcp list
# should show: gitlab   ✓ connected   (user scope)
```

If the MCP shows `✗ Failed to connect`, check that the PAT is still valid
(`Settings → Access Tokens` on `gitlab.gwdg.de`) and that
`GITLAB_API_URL` ends in `/api/v4` (not just the hostname).

---

## Summary table

| Name | Scope | Command | Notes |
|---|---|---|---|
| `spectrafit-reports` | project | `uv run --with mcp python scripts/mcp_spectrafit_reports.py` | built-in, `.mcp.json` |
| `memory` | user | `npx -y @modelcontextprotocol/server-memory` | V&V cycle history |
| `gitlab` | user | `npx -y @zereight/mcp-gitlab` | GWDG GitLab, needs PAT |
| `rrt` | project | `uvx --from repo-release-tools[mcp] rrt-mcp` | built-in, `.mcp.json` |
| `analyzer` | project | `uvx mcp-server-analyzer` | built-in, `.mcp.json` |
