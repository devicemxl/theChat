# Agent Loop for Code Mode (planned)

| key             | value                                                          |
|-----------------|----------------------------------------------------------------|
| tipo            | technical document · planned feature design                    |
| tema            | agent loop · tool calling · code assistance                    |
| titulo          | Agent Loop for theChat Code Mode                               |
| maturity        | design plan — no implementation exists yet                     |
| confidence      | medium (concept) · low (final implementation)                  |
| material origen | design discussions through August 2026                         |
| fecha           | 2026-08-31                                                     |
| mantenedor      | David                                                          |

## 1. Status

The toolbar in the current build has a "chat / code" radio toggle. Switching
to "code" today sets `st.session_state.agent_mode = "code"` and updates a
status message. Nothing else happens. There is no tool calling, no filesystem
access, no git integration.

This document describes what code mode should do when it is built. Numbers
(iteration limits, timeouts) are starting points that will be tuned once the
loop runs against real tasks.

## 2. What code mode should do

When the user is in code mode and sends a message, the LLM gets access to a
small set of tools for exploring and modifying a local project directory. The
model runs a loop — call a tool, receive the result, decide the next step —
until it produces a final response. Any file modification produces a git diff
that the user reviews and approves before it becomes a commit.

The goal is a lightweight code assistant that works against the current
working directory, backed by git for safety, with no external services and
no permissions to overwrite anything the user did not approve.

## 3. Component layout

```
User in code mode
      │
      ▼
views/chat.py
      │
      ▼
Agent loop (new module — e.g. llm/agent.py)
      │
      ├─► LLM call with tool schemas
      │
      ├─► Tool executor (new module — e.g. tools/)
      │        │
      │        ├─► Filesystem tools (list, search, read, write)
      │        │        └─► Path validation + exclusion lists
      │        │
      │        └─► Git tools (status, diff, log — read only)
      │                 └─► Subcommand allowlist
      │
      └─► Approval flow
               │
               ▼
       git commit + push (if approved)
       or revert to snapshot (if rejected)
```

## 4. Tools

Each tool is described by name, description, and JSON schema for parameters.
Definitions are translated to each provider's function-calling format at
request time.

### 4.1 Exploration (read-only)

**`list_directory(path, max_results=50)`** — direct children of a path with
type, size, extension. Excludes noisy directories (`venv/`, `__pycache__/`,
`node_modules/`, `.git/`, `build/`, `dist/`, hidden dirs). Paginated.

**`find_files(pattern, root=".", max_results=100)`** — glob search across
the project. Same exclusion rules.

**`grep(text, root=".", extensions=None, max_results=50)`** — text search in
allowed files. Returns paths, line numbers, and context lines.

### 4.2 Reading

**`read_file(path, start=None, end=None)`** — text file content or a line
range. Allowed extensions only. Path must resolve inside the project root
and must not target sensitive files (`.env`, `.git/`, key files, etc.).

### 4.3 Writing

**`write_file(path, content)`** — create or overwrite a text file. Same
validation as `read_file`, plus: only text extensions, no writes to hidden
files or system directories.

### 4.4 Git (read-only)

**`git_status()`** — output of `git status --porcelain`.

**`git_diff(scope="working_tree")`** — working tree diff or index diff
(`--cached`).

**`git_log(max_commits=10)`** — output of `git log --oneline -N`.

Any git subcommand that mutates the repository (`commit`, `push`, `pull`,
`checkout`, `merge`, `rebase`, `stash`, `add`, `rm`) is rejected at the
allowlist level, not at the argument parser. The loop never executes git
writes on its own; only the approval flow does.

## 5. Loop

1. **Compose messages**: current history + tool results from prior turns +
   system prompt describing the tools and rules.
2. **Call the LLM** with the tool schemas attached.
3. **Branch on response**:
   - Plain text → the loop terminates and the response is shown.
   - Tool calls → the executor validates and runs each tool, results are
     appended to the message list, go to step 2.
4. **Iteration cap**: 10 iterations max. If reached, the loop stops and
   surfaces a warning to the user.

## 6. Multi-provider tool calling

Function calling formats differ across providers. The agent module
translates a single internal tool schema into the format each provider
expects, and normalizes the response back to an internal shape.

- **DeepSeek, Mistral, Anthropic**: OpenAI-compatible `tools` array and
  `tool_calls` in the response.
- **Gemini**: `function_declarations` and `functionCall` in the response.

Streaming complicates this: tool arguments may arrive in fragments and
must be reassembled before execution. The agent module reconstructs
complete tool calls before dispatching.

## 7. Streamlit integration

**Mode toggle**: already present in the toolbar. Enabling code mode is the
switch that includes tool schemas in the request.

**Step visibility**: while the loop runs, each tool call is rendered
inside the assistant's `st.chat_message` block, in an expander showing
name, arguments, and result. This keeps the transcript inspectable without
overwhelming the reader.

**Approval flow**: after the final response, if any `write_file` calls
happened, an approval panel appears below the response with the aggregated
git diff and two buttons: "Approve and commit" / "Discard changes".

**Persistence**: tool calls and their results are stored in the `messages`
table as regular messages with a distinct role or a JSON payload — TBD
during implementation. The exact shape must survive export/import.

## 8. Context management

- The history sent to the LLM includes tool calls and results, but truncates
  long tool outputs (a `list_directory` on a huge repo, a `grep` with too
  many hits). The tool prompt instructs the model to refine queries when it
  hits truncation.
- Iteration cap (default 10) as above.
- Per-turn tool call cap (default 5): if the model requests more, the extras
  are deferred until the next turn.

## 9. Safety

### 9.1 Path validation

Every path passed to a tool is normalized (resolves `..`, follows symlinks)
and checked against the absolute path of the project root. Anything outside
is rejected. A deny list of file/directory names (`.env`, `.git/config`,
private key patterns) is applied on top.

### 9.2 Git subcommand allowlist

`git` is invoked through `subprocess.run` with argument lists (never shell
strings). The first argument after `git` is checked against the allowlist.
Anything else returns an error to the model.

### 9.3 Snapshot before mutation

Before the loop runs in code mode (and only in code mode), the middleware
executes `git add -A && git commit -m "snapshot before agent <timestamp>"`
if there are uncommitted changes. This provides a clean revert point that
survives whatever the loop does.

### 9.4 User opt-in

Code mode must be explicitly enabled by the user in the toolbar for each
session. It does not persist across restarts. The push step of the approval
flow requires a separate confirmation.

## 10. Approval flow in detail

1. **Session starts in code mode**: verify the working directory is a git
   repo; if not, disable code mode and tell the user.
2. **Before the first agent turn** that could write files: run the snapshot
   commit if there are uncommitted changes.
3. **Agent loop runs**: writes are applied to the working tree
   incrementally as the model produces them.
4. **User reviews**: the aggregated diff is shown in the approval panel.
5. **Approve**: `git add -A && git commit` with a message (LLM-suggested
   or user-typed), then `git push` if the user confirms push separately.
6. **Discard**: `git checkout -- .` (unstaged changes) and, if the model
   also created new files, `git clean -fd` limited to non-ignored paths.
   The snapshot commit stays as a rollback point.

## 11. Error handling

- **Tool failure**: return an error object to the LLM. The model may retry
  with corrected arguments, change strategy, or abandon the task.
- **LLM timeout**: same treatment as any provider failure in the base chat
  flow. Surface the error, break the loop.
- **Loop iteration cap hit**: stop, surface a warning message, keep any
  partial changes for the user to review or discard.

## 12. Out of scope

- Command execution beyond git (running tests, builds, arbitrary shell).
  A separate sandboxed command tool may come later, but not in the first
  iteration.
- Multi-repo operations.
- Remote deployment hooks.
- Partial approval of file changes (approve some, discard others). The
  first iteration is all-or-nothing.
- Cross-turn state beyond message history (no scratchpad, no persistent
  agent memory).
