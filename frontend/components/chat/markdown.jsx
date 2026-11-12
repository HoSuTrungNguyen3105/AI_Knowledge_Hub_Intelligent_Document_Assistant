"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

// Renders assistant Markdown (GFM tables, lists, code fences). Content is treated
// as text; raw HTML is not enabled, so model output cannot inject markup.
export function Markdown({ content }) {
  return (
    <div className="markdown">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content || ""}</ReactMarkdown>
    </div>
  );
}