"use client";

/* Architecture map — renders the backend-built payload
   (services/architecture_map.py) in the exact structure of the
   reference repository map: eyebrow, title, intro, language chips,
   a layered SVG diagram with legend, three reading cards, a scope
   note and a source foot line. All geometry (node positions, wire
   paths, view box) comes precomputed in the payload; this component
   only draws it. Styles live in code-analyzer.css under .cam-*. */

function trunc(text, max = 32) {
  if (!text || text.length <= max) return text;
  return `${text.slice(0, max - 1)}…`;
}

function NodeGroup({ node }) {
  const cx = node.x + node.w / 2;
  const titleX = node.center ? cx : node.x + 17;
  const anchor = node.center ? "middle" : undefined;
  return (
    <g className={`cam-node ${node.kind}`}>
      <rect x={node.x} y={node.y} width={node.w} height={node.h} rx="11" />
      <text x={titleX} y={node.y + 29} textAnchor={anchor} className="cam-ntitle">
        {node.title}
      </text>
      {node.subs.map((sub, i) => (
        <text
          key={i}
          x={titleX}
          y={node.y + 51 + i * 19}
          textAnchor={anchor}
          className="cam-nsub"
        >
          {trunc(sub)}
        </text>
      ))}
      {node.tiny.map((line, i) => (
        <text
          key={i}
          x={titleX}
          y={node.y + 51 + node.subs.length * 19 + 6 + i * 16}
          textAnchor={anchor}
          className="cam-ntiny"
        >
          {trunc(line, 36)}
        </text>
      ))}
    </g>
  );
}

export default function ArchitectureMap({ map }) {
  if (!map) return null;
  const { view_box: viewBox, cards } = map;
  return (
    <div className="cam">
      <div className="cam-eyebrow">{map.eyebrow}</div>
      <h1 className="cam-h1">{map.title}</h1>
      <p className="cam-intro">{map.intro}</p>
      <div className="cam-chips" aria-label="Repository language breakdown">
        {map.chips.map((chip, i) => (
          <span key={i} className="cam-chip">
            {chip.value != null ? (
              <>
                <strong>{chip.value}</strong> {chip.label}
              </>
            ) : (
              chip.label
            )}
          </span>
        ))}
      </div>
      <div className="cam-diagram" aria-label="Scrollable architecture diagram">
        <svg
          viewBox={`0 0 ${viewBox.w} ${viewBox.h}`}
          role="img"
          aria-label="Sơ đồ kiến trúc của dự án"
        >
          <defs>
            <pattern id="cam-grid" width="36" height="36" patternUnits="userSpaceOnUse">
              <path d="M36 0H0V36" fill="none" stroke="#23364d" strokeWidth=".55" />
            </pattern>
            <marker id="cam-arrow" markerWidth="9" markerHeight="8" refX="8" refY="4" orient="auto">
              <path d="M0 0L9 4L0 8Z" fill="#8ca3bd" />
            </marker>
          </defs>
          <rect width={viewBox.w} height={viewBox.h} fill="url(#cam-grid)" opacity=".46" />
          {map.lane_marks.map((mark, i) => (
            <text key={i} x="22" y={mark.y} className="cam-lane">
              {mark.label}
            </text>
          ))}
          {map.wires.map((wire, i) => (
            <path key={i} className={`cam-wire ${wire.cls || ""}`} d={wire.d} />
          ))}
          {map.nodes.map((node) => (
            <NodeGroup key={node.key} node={node} />
          ))}
        </svg>
        <div className="cam-legend">
          {map.legend.map((item, i) => (
            <span key={i}>
              <i style={{ background: item.color }} />
              {item.label}
            </span>
          ))}
        </div>
      </div>
      <section className="cam-cards">
        <article className="cam-card">
          <h2>Where to start reading</h2>
          <ol>
            {cards.reading.map((item, i) => (
              <li key={i}>
                <span className="cam-path">{item.path}</span>
                {item.text}
              </li>
            ))}
          </ol>
        </article>
        <article className="cam-card">
          <h2>What the diagram follows</h2>
          {cards.follows.map((paragraph, i) => (
            <p key={i}>{paragraph}</p>
          ))}
        </article>
        <article className="cam-card">
          <h2>Language counts</h2>
          <p>{cards.languages.note}</p>
          <p>{cards.languages.text}</p>
        </article>
      </section>
      <div className="cam-status">
        <strong>Scope note:</strong> {map.scope_note}
      </div>
      <p className="cam-foot">{map.foot}</p>
    </div>
  );
}
