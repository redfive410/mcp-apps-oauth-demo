import { useMemo } from "react";
import { marked } from "marked";
import "./widget.css";

function toolResultToMarkdown(toolResult) {
  const data = toolResult?.structuredContent || toolResult;
  if (!data) return null;

  if (typeof data === "string") return data;

  const lines = [];
  for (const [key, value] of Object.entries(data)) {
    if (key.startsWith("_")) continue;
    const displayValue =
      typeof value === "object" ? JSON.stringify(value, null, 2) : String(value);
    lines.push(`**${key}:** ${displayValue}`);
  }
  return lines.join("\n\n");
}

export default function ToolOutputWidget({ toolResult }) {
  const markdown = useMemo(() => toolResultToMarkdown(toolResult), [toolResult]);

  if (!markdown) {
    return (
      <div className="tool-output-container">
        <div className="tool-output-empty">
          No tool output yet. Output will appear here when a tool is invoked.
        </div>
      </div>
    );
  }

  const html = marked.parse(markdown);

  return (
    <div className="tool-output-container">
      <div
        className="tool-output-markdown"
        dangerouslySetInnerHTML={{ __html: html }}
      />
    </div>
  );
}
