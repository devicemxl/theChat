# UI/UX

| key             | value                                                             |
|-----------------|-------------------------------------------------------------------|
| tipo            | technical document · user interface design                        |
| tema            | UI/UX · Streamlit · personal chat interface                       |
| titulo          | theChat User Interface                                            |
| maturity        | current implementation + planned additions                        |
| confidence      | high (current) · medium (planned)                                 |
| material origen | development log through August 2026                               |
| fecha           | 2026-08-31                                                        |
| mantenedor      | David                                                             |

## 1. Scope

This document describes the interface as it exists today and the additions
planned for the RAG phases. Current-state sections describe code that ships.
Planned sections describe intent — subject to revision when they land.

The interface uses Streamlit 1.62+. Design targets a single-user local app
running on desktop or mobile browser.

## 2. Navigation

Three top-level views registered through `st.navigation`:

- **Chat** — the main conversation interface (default view).
- **Projects** — CRUD for projects: create, edit, delete.
- **Data** — placeholder page for the planned RAG ingestion UI.

Navigation lives in Streamlit's own sidebar section, above whatever each
view adds. `initial_sidebar_state="expanded"` so the nav is visible on
first load; a user in a narrower viewport can collapse it.

The sidebar contents beyond navigation are page-scoped. Only `views/chat.py`
renders the conversation history / export / import / stats sections.

## 3. Chat view

### 3.1 Top toolbar

An `st.expander` at the top of the view holds all session controls in six
columns:

| col | control                                                    |
|-----|------------------------------------------------------------|
| 1   | AI provider (DeepSeek / Gemini / Mistral / Anthropic)      |
| 2   | Agent mode (chat / code) — code mode has no effect yet     |
| 3   | Effort (bajo / medio / alto) — maps to temperature or `reasoning_effort` depending on provider |
| 4   | File attachment uploader (multi-file)                      |
| 5   | Project selector (— Sin proyecto — / list of projects)     |
| 6   | Clear-conversation button (opens confirmation modal)       |

Below the columns, an `st.info` line shows the most relevant status message,
ordered by priority:

1. API key missing warning (blocks the view — returns from `main`)
2. Attached files summary (`📎 Archivos adjuntos: ...`)
3. Code mode notice
4. Active project system-prompt indicator (`🔧 System-prompt del
   proyecto ... activo`)
5. Default (`Enjoy It`)

Only one line shows at a time. Lower-priority messages are suppressed when
higher-priority ones apply.

The expander header itself shows conversation metadata:

```
Conversación #<id> | Mensajes: <N> | Reformulaciones: <N> | Provider: <name>
```

### 3.2 Message display

Standard `st.chat_message` blocks, `user` and `assistant` roles, with
Streamlit's default alignment and background.

When a user turn includes file attachments, the file contents render in
`st.expander` blocks below the visible prompt text — one expander per file,
labeled with the filename, containing the extracted text as a code block.

Each assistant turn ends with a copy-to-clipboard button
(`ui/components.py::add_copy_button`) that copies the Markdown source of
the message.

If a message was truncated (streaming interrupted, saved as partial), a
caption `⚠️ *Mensaje truncado*` appears below it. If a message resulted
from one or more reformulations, a caption
`🔄 *Reformulado N veces*` appears below it.

### 3.3 Input area

`st.chat_input` at the bottom. Files are attached via the toolbar's uploader
before typing, then sent along with the message. The uploader auto-resets
after each send by rotating a session_state key (`uploader_key`).

### 3.4 Streaming feedback

Assistant responses stream token-by-token into an `st.empty()` placeholder
inside the assistant's `st.chat_message` block, with a trailing `▌` cursor
during the stream. On completion, the placeholder is replaced with the
final text.

If the user reloads or navigates during a stream, the partial response is
saved as a truncated message on the next turn, so nothing is silently lost.

### 3.5 Sidebar (chat view only)

- Session timestamp caption
- "New Conversation" button
- **📚 Historial** — grouped by project:
  - One expander per project (labeled with emoji, name, chat count)
  - Chats render as compact rows: `[▶️/📄 Title] [✏️] [🗑️]`
  - `▶️` marks the currently active chat, styled as primary button
  - Empty projects show their header with `_Sin conversaciones_`
  - The group containing the active chat auto-expands
  - A "Sin proyecto" group always appears at the end
- Rename and delete each open a `@st.dialog` modal
- **📤 Exportar** — download current chat or full history as JSON
- **📂 Importar** — upload JSON to restore conversations
- **📊 Estadísticas** — conversation count, message count, truncation
  metrics

## 4. Projects view

### 4.1 List

Each project renders inside `st.container(border=True)`:

```
┌────────────────────────────────────────────┐
│ [color] 🌱 Raitec  · 12 chat(s)     ✏️ 🗑️ │
│   Description text here.                   │
│   ▸ Ver system prompt                      │
└────────────────────────────────────────────┘
```

- A colored square (`color` field) as an inline marker
- Emoji + name in bold
- Chat count in muted text
- Optional description as caption
- Optional system prompt in a nested expander
- Edit and delete buttons per row

### 4.2 Create / edit / delete modals

Three `@st.dialog` modals:

- **New project**: name (required, UNIQUE), emoji (free text input, default
  📁), color (selectbox from 8-color palette with a color-strip preview),
  description, system prompt.
- **Edit project**: same fields, pre-populated. Prompt hint reminds the user
  that a non-empty prompt replaces the default.
- **Delete project**: shows how many chats will be reassigned to "Sin
  proyecto", warns that the action is not undoable. Includes a note that
  the backup-to-zip feature is not implemented yet.

All modals validate name uniqueness (via `sqlite3.IntegrityError`) and
non-empty name (via `ValueError` raised by `create_project` /
`update_project`).

## 5. Data view (stub)

Currently: a title, an "under construction" info block, and a bullet list
outlining the planned RAG components. When the RAG ingestion phase lands,
this view will host the multi-file uploader, destination selector, and
progress log described in `pipeline.md`.

## 6. Interaction patterns

### 6.1 Confirmations

Destructive actions use `@st.dialog` modals with a warning message, a red
primary button for the destructive action, and a secondary cancel button:

- Clear current conversation (from chat toolbar)
- Delete conversation (from sidebar row)
- Delete project (from projects list)

The modals do not block the underlying view; canceling simply reruns.

### 6.2 Herencia de proyecto on new conversation

When "New Conversation" is pressed while inside a chat that belongs to a
project, the new conversation is created inside the same project. The user
can move it to another project (or to "Sin proyecto") via the toolbar
selector.

### 6.3 Empty-conversation cleanup

The cleanup is silent — no toast, no confirmation. Empty conversations
are removed on startup and on switch. The active conversation is always
protected from the sweep.

### 6.4 System-prompt substitution feedback

When the active chat belongs to a project with a system prompt, the
toolbar's status line makes this visible with the project's emoji and
name. This is the only surface where the substitution is announced;
there is no per-message annotation.

## 7. Visual design

- Streamlit defaults for typography and spacing.
- Custom CSS in `ui/components.py::load_custom_css` for: sidebar max width
  (300px), hidden menu, adjusted main container padding, expander border
  for user-attachment blocks.
- The custom CSS loads in `app.py`, once per session.
- Project colors from a fixed 8-color palette (`utils/constants.py`).
  Emojis are free text — no curated list.

## 8. Mobile

The chat is used primarily on mobile. Concessions and known limitations:

- Six-column toolbar wraps on narrow viewports; readable but not elegant.
- `@st.dialog` modals work correctly and are more usable than the previous
  inline-editing pattern.
- Sidebar collapses on narrow screens; user can still open it to navigate
  or check history.
- Streaming rendering is smooth on modern mobile Chrome / Safari.

## 9. Planned additions (not implemented)

### 9.1 RAG toggle in the toolbar

A toggle to enable/disable retrieval per session, once the retrieval phase
lands. Off by default; on requires the active chat to be in a project with
indexed documents.

### 9.2 Source panel below RAG-informed responses

An `st.expander` below each assistant response that used retrieval,
listing chunks with source document names, similarity scores, and snippets.

### 9.3 Reindex indicator

Chats with `pending_reindex = 1` show a small `🔄` next to their title in
the sidebar. Purely visual — no interaction.

### 9.4 Move-a-chat confirmation

When RAG is populated, changing a chat's project via the selector opens a
modal explaining that reindexing is required, offering blocking or
background modes.

### 9.5 Agent loop visualization

When code mode is actually implemented (see `agentloop.md`), each tool call
renders in an expander inside the assistant's message block, showing the
tool name, arguments, and result. Approval panel appears below the final
response summarizing the aggregated diff.

## 10. Accessibility

Streamlit's default keyboard navigation covers most interactions.
`@st.dialog` modals trap focus while open. Color is never the only signal
for state (buttons carry text, project markers appear next to labels, not
alone).
