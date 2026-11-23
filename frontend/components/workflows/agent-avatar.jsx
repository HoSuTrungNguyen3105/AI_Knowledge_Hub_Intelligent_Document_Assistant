"use client";

// Chibi robot character for the office simulation, drawn as inline SVG so
// it stays crisp at any size and needs no image assets. Poses are driven
// purely by CSS classes:
// - walking: legs step alternately, arms swing, body bobs (agent is moving
//   between the desk and a floor waypoint)
// - working: arms type quickly (agent sits at its desk on a real task)
// - idle: gentle breathing bob; eyes blink in every state.
// The accent colour is the role colour used across the workspace.
export function AgentAvatar({ color = "#7c3aed", role = "member", walking = false, working = false }) {
  const pose = walking ? "walking" : working ? "working" : "idle";
  return <svg className={`wf-bot wf-bot-${pose}`} viewBox="0 0 120 142" role="img"
    aria-label={`Robot Agent ${role}`}>
    {/* legs */}
    <g className="wf-bot-leg left">
      <rect x="46" y="104" width="11" height="22" rx="5.5" fill="#cbd5e1" />
      <ellipse cx="51" cy="130" rx="10" ry="5.5" fill={color} />
    </g>
    <g className="wf-bot-leg right">
      <rect x="63" y="104" width="11" height="22" rx="5.5" fill="#cbd5e1" />
      <ellipse cx="69" cy="130" rx="10" ry="5.5" fill={color} />
    </g>
    {/* arms */}
    <g className="wf-bot-arm left">
      <rect x="26" y="66" width="10" height="30" rx="5" fill="#e2e8f0" />
      <circle cx="31" cy="99" r="6" fill={color} />
    </g>
    <g className="wf-bot-arm right">
      <rect x="84" y="66" width="10" height="30" rx="5" fill="#e2e8f0" />
      <circle cx="89" cy="99" r="6" fill={color} />
    </g>
    {/* torso */}
    <rect x="38" y="58" width="44" height="50" rx="15" fill="#f8fafc" stroke="#cbd5e1" strokeWidth="1.5" />
    <rect x="47" y="68" width="26" height="20" rx="7" fill={color} opacity="0.16" />
    <circle className="wf-bot-heart" cx="60" cy="78" r="5.5" fill={color} />
    <rect x="50" y="94" width="20" height="5" rx="2.5" fill="#cbd5e1" />
    {/* head */}
    <rect x="52" y="6" width="3.5" height="12" rx="1.75" fill="#94a3b8" />
    <circle cx="54" cy="5" r="4.5" fill={color} className="wf-bot-antenna" />
    {role === "coordinator" && (
      <path d="M38 22 L45 10 L54 19 L60 8 L66 19 L75 10 L82 22 Z" fill="#f59e0b" stroke="#d97706" strokeWidth="1.5" />
    )}
    <rect x="20" y="34" width="9" height="18" rx="4.5" fill={color} />
    <rect x="91" y="34" width="9" height="18" rx="4.5" fill={color} />
    <rect x="27" y="16" width="66" height="52" rx="20" fill="#ffffff" stroke="#cbd5e1" strokeWidth="1.5" />
    <rect x="34" y="23" width="52" height="38" rx="15" fill="#0f172a" />
    <g className="wf-bot-eyes">
      <rect x="44" y="36" width="8" height="12" rx="4" fill="#38bdf8" />
      <rect x="68" y="36" width="8" height="12" rx="4" fill="#38bdf8" />
    </g>
    <path d="M53 53 Q60 58 67 53" stroke="#38bdf8" strokeWidth="2.4" fill="none" strokeLinecap="round" />
    <circle cx="40" cy="50" r="3.4" fill="#fda4af" opacity="0.85" />
    <circle cx="80" cy="50" r="3.4" fill="#fda4af" opacity="0.85" />
  </svg>;
}
