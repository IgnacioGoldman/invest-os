import { memo, useMemo, useState, type ReactNode } from "react";
import { Eye, FilePlus2, Pencil, Save, Trash2 } from "lucide-react";
import { formatDateTime } from "../format";
import type { Note } from "../api";

type Props = {
  notes: Note[];
  selectedNoteId: string | null;
  title: string;
  content: string;
  dirty: boolean;
  saving: boolean;
  status: string | null;
  onSelectNote: (note: Note) => void;
  onNewNote: () => void;
  onTitleChange: (title: string) => void;
  onContentChange: (content: string) => void;
  onSave: () => void;
  onDelete: () => void;
};

type PreviewBlock =
  | { kind: "heading"; level: 1 | 2 | 3; text: string }
  | { kind: "paragraph"; text: string }
  | { kind: "quote"; text: string }
  | { kind: "code"; text: string }
  | { kind: "list"; items: string[] };

const inlinePattern = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)/g;

const renderInline = (text: string): ReactNode[] => {
  const parts = text.split(inlinePattern).filter(Boolean);
  return parts.map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return <code key={index}>{part.slice(1, -1)}</code>;
    }
    if (part.startsWith("*") && part.endsWith("*")) {
      return <em key={index}>{part.slice(1, -1)}</em>;
    }
    return <span key={index}>{part}</span>;
  });
};

const markdownBlocks = (content: string): PreviewBlock[] => {
  const blocks: PreviewBlock[] = [];
  const lines = content.replace(/\r\n/g, "\n").split("\n");
  let paragraph: string[] = [];
  let list: string[] = [];
  let code: string[] = [];
  let inCodeBlock = false;

  const flushParagraph = () => {
    if (paragraph.length) {
      blocks.push({ kind: "paragraph", text: paragraph.join(" ") });
      paragraph = [];
    }
  };
  const flushList = () => {
    if (list.length) {
      blocks.push({ kind: "list", items: list });
      list = [];
    }
  };

  for (const line of lines) {
    if (line.trim().startsWith("```")) {
      if (inCodeBlock) {
        blocks.push({ kind: "code", text: code.join("\n") });
        code = [];
        inCodeBlock = false;
      } else {
        flushParagraph();
        flushList();
        code = [];
        inCodeBlock = true;
      }
      continue;
    }
    if (inCodeBlock) {
      code.push(line);
      continue;
    }

    const trimmed = line.trim();
    if (!trimmed) {
      flushParagraph();
      flushList();
      continue;
    }

    const heading = /^(#{1,3})\s+(.+)$/.exec(trimmed);
    if (heading) {
      flushParagraph();
      flushList();
      blocks.push({ kind: "heading", level: heading[1].length as 1 | 2 | 3, text: heading[2] });
      continue;
    }

    const bullet = /^[-*]\s+(.+)$/.exec(trimmed);
    if (bullet) {
      flushParagraph();
      list.push(bullet[1]);
      continue;
    }

    if (trimmed.startsWith(">")) {
      flushParagraph();
      flushList();
      blocks.push({ kind: "quote", text: trimmed.replace(/^>\s?/, "") });
      continue;
    }

    paragraph.push(trimmed);
  }

  flushParagraph();
  flushList();
  if (inCodeBlock) {
    blocks.push({ kind: "code", text: code.join("\n") });
  }
  return blocks;
};

const MarkdownPreview = memo(function MarkdownPreview({ content }: { content: string }) {
  const blocks = useMemo(() => markdownBlocks(content), [content]);
  if (!blocks.length) {
    return <p className="notes-preview-empty">Nothing to preview yet.</p>;
  }
  return (
    <div className="notes-markdown-preview">
      {blocks.map((block, index) => {
        if (block.kind === "heading") {
          const Tag = `h${block.level}` as "h1" | "h2" | "h3";
          return <Tag key={index}>{renderInline(block.text)}</Tag>;
        }
        if (block.kind === "list") {
          return (
            <ul key={index}>
              {block.items.map((item, itemIndex) => (
                <li key={itemIndex}>{renderInline(item)}</li>
              ))}
            </ul>
          );
        }
        if (block.kind === "quote") {
          return <blockquote key={index}>{renderInline(block.text)}</blockquote>;
        }
        if (block.kind === "code") {
          return <pre key={index}>{block.text}</pre>;
        }
        return <p key={index}>{renderInline(block.text)}</p>;
      })}
    </div>
  );
});

export const NotesPanel = memo(function NotesPanel({
  notes,
  selectedNoteId,
  title,
  content,
  dirty,
  saving,
  status,
  onSelectNote,
  onNewNote,
  onTitleChange,
  onContentChange,
  onSave,
  onDelete,
}: Props) {
  const [mode, setMode] = useState<"write" | "preview">("write");
  const hasSelectedNote = Boolean(selectedNoteId);
  const saveDisabled = saving || !dirty;

  return (
    <section className="panel notes-panel">
      <div className="panel-heading">
        <h2>Notes</h2>
        <div className="panel-heading-actions">
          <span className={dirty ? "notes-save-status dirty" : "notes-save-status"}>
            {dirty ? "Unsaved" : hasSelectedNote ? "Saved" : "Draft"}
          </span>
          <button type="button" className="notes-new-button" onClick={onNewNote}>
            <FilePlus2 size={15} aria-hidden="true" />
            New
          </button>
          <button type="button" className="notes-save-button" onClick={onSave} disabled={saveDisabled}>
            <Save size={15} aria-hidden="true" />
            {saving ? "Saving" : "Save"}
          </button>
        </div>
      </div>

      <div className="notes-layout">
        <aside className="notes-list" aria-label="Saved notes">
          {notes.length === 0 && <p>No saved notes.</p>}
          {notes.map((note) => (
            <button
              type="button"
              key={note.id}
              className={note.id === selectedNoteId ? "active" : ""}
              onClick={() => onSelectNote(note)}
            >
              <strong>{note.title}</strong>
              <span>{formatDateTime(note.updated_at)}</span>
            </button>
          ))}
        </aside>

        <div className="notes-editor">
          <input
            className="notes-title-input"
            value={title}
            onChange={(event) => onTitleChange(event.target.value)}
            placeholder="Note title"
          />
          <div className="notes-editor-tabs" aria-label="Notes editor mode">
            <button type="button" className={mode === "write" ? "active" : ""} onClick={() => setMode("write")}>
              <Pencil size={15} aria-hidden="true" />
              Write
            </button>
            <button type="button" className={mode === "preview" ? "active" : ""} onClick={() => setMode("preview")}>
              <Eye size={15} aria-hidden="true" />
              Preview
            </button>
          </div>

          {mode === "write" ? (
            <textarea
              value={content}
              onChange={(event) => onContentChange(event.target.value)}
              placeholder="# Investment note&#10;&#10;- What changed?&#10;- What decision did I make?&#10;- What should I review later?"
            />
          ) : (
            <MarkdownPreview content={content} />
          )}

          <div className="notes-footer">
            {status && <span>{status}</span>}
            {hasSelectedNote && (
              <button type="button" className="notes-delete-button" onClick={onDelete}>
                <Trash2 size={15} aria-hidden="true" />
                Delete
              </button>
            )}
          </div>
        </div>
      </div>
    </section>
  );
});
