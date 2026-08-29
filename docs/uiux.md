# User Interface Proposal[](#user-interface-proposal)

| key             | value                                                                |
|-----------------|----------------------------------------------------------------------|
| tipo            | technical document · user interface design                           |
| tema            | UI/UX · Streamlit · RAG chat interface                               |
| titulo          | Multi-Project RAG Chat User Interface                                |
| parte           | VI — System Architecture                                             |
| maturity        | draft for review                                                     |
| confidence      | high (concept) · medium (final implementation)                       |
| material origen | June 2026 conversation — UI design for multi-project RAG integration |
| fecha           | 2026-06-08                                                           |
| mantenedor      | David                                                                |

## 1. Layout Overview[](#1-layout-overview)

The application adopts a three-tab structure to separate the main functional areas. The tabs are Chat, Projects, and Ingestion. This organization provides clear navigation and prevents cognitive overload by isolating distinct workflows.

The sidebar maintains consistent access to conversation history, export/import functionality, statistics, and API configuration across all tabs. This persistent sidebar ensures that global controls remain accessible regardless of the active tab.

## 2. Chat Tab[](#2-chat-tab)

### 2.1 Header Area[](#2-1-header-area)

The header displays the active project name with a project selector dropdown. A badge indicates whether RAG search is enabled for the current session. The header also shows conversation metadata including message count, reformulation count, and active provider.

A toggle switch labeled "Search in Project" controls whether RAG retrieval is active. When disabled, the chat operates as a standard conversational interface without context enrichment.

### 2.2 Message Display[](#2-2-message-display)

User messages appear right-aligned with a distinct background color. Assistant messages appear left-aligned with standard styling. When a user message includes file attachments, the files appear in expandable panels below the message text, each showing the filename and content preview.

Assistant responses that used RAG context display a "Sources" expander below the response text. This expander lists the documents retrieved and used, showing the document title, similarity score, and a snippet of the content. Users can expand each source to view the full text.

### 2.3 Input Area[](#2-3-input-area)

The input area consists of a chat input field for text entry and a file uploader for attachments. The file uploader accepts multiple files and displays the list of selected files with their sizes above the input field. After sending a message, the uploader resets automatically.

The input area includes contextual actions near the input field, such as a "Clear Conversation" button to reset the current session.

## 3. Projects Tab[](#3-projects-tab)

### 3.1 Project List[](#3-1-project-list)

The projects tab displays all available projects in a structured list. Each project entry shows the project name, description, creation date, document count, and storage size. A status indicator shows whether the project index is loaded and ready for search.

Clicking on a project expands its details, showing global tags, recent documents, and usage statistics. The expanded view includes action buttons for loading the project, editing project metadata, and deleting the project.

### 3.2 Create Project[](#3-2-create-project)

A "New Project" button opens a form with fields for project name, description, and global tags. The system validates that the project name is unique and creates the directory structure, database, and index upon submission.

### 3.3 Project Configuration[](#3-3-project-configuration)

Each project has a configuration panel accessible from the project list. This panel allows editing the project name, description, and global tags. It also displays the embedding model in use and allows changing the model if multiple options are available.

## 4. Ingestion Tab[](#4-ingestion-tab)

### 4.1 File Upload Area[](#4-1-file-upload-area)

The ingestion tab provides a large drop zone for uploading multiple files. Supported file types include text, markdown, PDF, DOCX, CSV, JSON, and code files. The system displays the list of selected files with their sizes and types before processing.

### 4.2 Processing Options[](#4-2-processing-options)

Users select the destination project from a dropdown. They choose between two processing modes: Quick and Deep. Quick mode generates embeddings directly from the extracted text. Deep mode uses a language model to extract semantic units, generate summaries, and assign tags.

Advanced options include chunk size, overlap percentage, and manual tag assignment. These options appear in an expandable "Advanced Settings" panel.

### 4.3 Progress and Logs[](#4-3-progress-and-logs)

During processing, the interface displays a progress bar showing the percentage of documents processed. A live log area shows real-time status messages for each document, including extraction time, embedding time, and any errors encountered.

Upon completion, the system shows a summary with the number of documents processed, the number of semantic units created, and the total processing time. Errors are highlighted for user attention.

## 5. Sidebar[](#5-sidebar)

### 5.1 Conversation Management[](#5-1-conversation-management)

The sidebar includes a "New Conversation" button and a history section listing all conversations. Each conversation entry shows its title, message count, and last update time. Users can load, rename, or delete conversations from this section.

### 5.2 Export and Import[](#5-2-export-and-import)

An export section provides buttons to download the current conversation or all conversations as JSON files. An import section allows uploading JSON files to restore previously exported conversations.

### 5.3 Statistics[](#5-3-statistics)

A statistics section displays key metrics including total conversations, total messages, truncated messages, and conversations with truncation. These metrics use Streamlit's metric components for visual clarity.

### 5.4 API Configuration[](#5-4-api-configuration)

An API configuration section allows users to select the AI provider from a list of available options. The section displays the current API key status and provides a secure input field for updating keys when necessary.

## 6. Visual Design[](#6-visual-design)

### 6.1 Color Scheme[](#6-1-color-scheme)

The interface uses a clean, professional color palette. Primary actions use a distinct accent color, while secondary elements use neutral grays. User messages and assistant messages have distinct background colors for easy differentiation.

### 6.2 Typography[](#6-2-typography)

The interface uses standard system fonts with appropriate sizing. Headers use larger font sizes to establish hierarchy. Code blocks and file contents use monospace fonts for readability.

### 6.3 Responsive Layout[](#6-3-responsive-layout)

The layout adapts to different screen sizes. The sidebar collapses on smaller screens. The chat area maintains readability by adjusting message width. The projects and ingestion tabs stack vertically on narrow screens.

## 7. Interaction Patterns[](#7-interaction-patterns)

### 7.1 Project Switching[](#7-1-project-switching)

When the user switches projects, the system saves the current conversation state, loads the new project's index, and starts a fresh conversation context. A confirmation dialog appears if the current conversation has unsaved messages.

### 7.2 RAG Toggle[](#7-2-rag-toggle)

The RAG toggle provides immediate feedback. When enabled, a brief indicator appears showing that context retrieval is active. The system caches the search results for the current question to avoid redundant queries.

### 7.3 Source Display[](#7-3-source-display)

The "Sources" expander appears only when the assistant response used RAG context. Each source entry shows the document title, similarity score, and a snippet. Users can expand each source to view the full document content.

### 7.4 Error Handling[](#7-4-error-handling)

Error messages appear as toast notifications for transient issues and as inline alerts for persistent problems. The system provides clear guidance on how to resolve configuration errors, such as missing API keys or unavailable embedding models.

## 8. Accessibility Considerations[](#8-accessibility-considerations)

The interface supports keyboard navigation for all interactive elements. Color contrast meets WCAG guidelines for readability. Screen reader labels are provided for all form elements and interactive components.