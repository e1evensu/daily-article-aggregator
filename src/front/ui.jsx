// Shared UI atoms — badges, score visuals, icons
const { useState, useEffect, useRef, useMemo } = React;

// ---------- icons (lucide-style) ----------
export const Icon = ({ name, size = 14, stroke = 1.6, className = '' }) => {
  const props = { width: size, height: size, viewBox: '0 0 24 24', fill: 'none',
    stroke: 'currentColor', strokeWidth: stroke, strokeLinecap: 'round', strokeLinejoin: 'round',
    className };
  switch (name) {
    case 'inbox': return <svg {...props}><polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11L2 12v6a2 2 0 002 2h16a2 2 0 002-2v-6l-3.45-6.89A2 2 0 0016.76 4H7.24a2 2 0 00-1.79 1.11z"/></svg>;
    case 'newspaper': return <svg {...props}><path d="M4 22h16a2 2 0 002-2V4a2 2 0 00-2-2H8a2 2 0 00-2 2v16a2 2 0 01-2 2zm0 0a2 2 0 01-2-2v-9c0-1.1.9-2 2-2h2"/><path d="M18 14h-8M15 18h-5M10 6h8v4h-8z"/></svg>;
    case 'activity': return <svg {...props}><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>;
    case 'database': return <svg {...props}><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v6c0 1.66 4 3 9 3s9-1.34 9-3V5M3 11v6c0 1.66 4 3 9 3s9-1.34 9-3v-6"/></svg>;
    case 'bar': return <svg {...props}><line x1="12" y1="20" x2="12" y2="10"/><line x1="18" y1="20" x2="18" y2="4"/><line x1="6" y1="20" x2="6" y2="16"/></svg>;
    case 'sun': return <svg {...props}><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>;
    case 'moon': return <svg {...props}><path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/></svg>;
    case 'play': return <svg {...props}><polygon points="5 3 19 12 5 21 5 3"/></svg>;
    case 'refresh': return <svg {...props}><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/></svg>;
    case 'search': return <svg {...props}><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>;
    case 'x': return <svg {...props}><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>;
    case 'ext': return <svg {...props}><path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>;
    case 'arrowUp': return <svg {...props}><line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/></svg>;
    case 'arrowRight': return <svg {...props}><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>;
    case 'arrowDown': return <svg {...props}><line x1="12" y1="5" x2="12" y2="19"/><polyline points="19 12 12 19 5 12"/></svg>;
    case 'minus': return <svg {...props}><line x1="5" y1="12" x2="19" y2="12"/></svg>;
    case 'sliders': return <svg {...props}><line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/></svg>;
    case 'lock': return <svg {...props}><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0110 0v4"/></svg>;
    case 'clock': return <svg {...props}><circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15 14"/></svg>;
    case 'check': return <svg {...props}><polyline points="20 6 9 17 4 12"/></svg>;
    case 'alert': return <svg {...props}><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>;
    case 'rss': return <svg {...props}><path d="M4 11a9 9 0 019 9M4 4a16 16 0 0116 16"/><circle cx="5" cy="19" r="1"/></svg>;
    case 'github': return <svg {...props}><path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 00-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0020 4.77 5.07 5.07 0 0019.91 1S18.73.65 16 2.48a13.38 13.38 0 00-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 005 4.77a5.44 5.44 0 00-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 009 18.13V22"/></svg>;
    case 'api': return <svg {...props}><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>;
    case 'link': return <svg {...props}><path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71"/></svg>;
    default: return null;
  }
};

// ---------- score helpers ----------
export const scoreClass = (s) => s == null ? 's-low' : s < 30 ? 's-low' : s < 50 ? 's-mid' : s < 75 ? 's-high' : 's-top';

export const ScoreNum = ({ value, suffix }) => {
  if (value == null) return <span className="score-num s-low">—</span>;
  return (
    <span className={`score-num ${scoreClass(value)}`}>
      {value}{suffix && <span className="pct">{suffix}</span>}
    </span>
  );
};

export const ScoreBar = ({ value, threshold = 75 }) => {
  const w = Math.max(0, Math.min(100, value || 0));
  return (
    <div className="score-bar" title={`insight_score = ${value}`}>
      <div className={`score-bar-fill ${scoreClass(value)}`} style={{ width: w + '%' }} />
      <div className="score-bar-threshold" style={{ left: threshold + '%' }} />
    </div>
  );
};

// ---------- confidence ----------
export const Confidence = ({ value }) => {
  if (!value) return null;
  const labels = { tentative: 'tentative', firm: 'firm', confirmed: 'confirmed' };
  return (
    <span className={`confidence-chip ${value}`} title={`confidence = ${value}`}>
      <span className="conf-pips">
        <span className="pip"/><span className="pip"/><span className="pip"/>
      </span>
      {labels[value]}
    </span>
  );
};

export const Trend = ({ value }) => {
  if (!value) return null;
  const map = {
    emerging: { icon: 'arrowUp', label: 'emerging' },
    growing: { icon: 'arrowUp', label: 'growing' },
    stable: { icon: 'minus', label: 'stable' },
    declining: { icon: 'arrowDown', label: 'declining' },
  };
  const c = map[value]; if (!c) return null;
  return (
    <span className={`trend-chip ${value}`}>
      <Icon name={c.icon} size={11} stroke={2} />
      {c.label}
    </span>
  );
};

// ---------- health ----------
export const Health = ({ value, withLabel = true }) => {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
      <span className={`dot ${value}`} />
      {withLabel && <span style={{ fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--text-2)' }}>{value}</span>}
    </span>
  );
};

// ---------- credibility ----------
export const Credibility = ({ value }) => {
  if (!value || value === 'unknown') return null;
  const cls = value === 'high' ? 'solid-ok' : value === 'medium' ? 'solid-warn' : 'solid-fail';
  return <span className={`badge ${cls}`}>cred · {value}</span>;
};

// ---------- source pill ----------
export const SourceIcon = ({ type }) => {
  const map = { rss: 'rss', github_api: 'github', api: 'api', internal_api: 'database' };
  return <Icon name={map[type] || 'link'} size={11} />;
};

export const SourcePill = ({ source }) => {
  if (!source) return null;
  return (
    <span className="source-pill">
      <SourceIcon type={source.type} />
      <span>{source.name}</span>
    </span>
  );
};

export const buildById = (items) => Object.fromEntries(items.map((item) => [item.id, item]));

export const countBy = (items, keyFn) => {
  const counts = {};
  items.forEach((item) => {
    const key = keyFn(item);
    if (key == null) return;
    counts[key] = (counts[key] || 0) + 1;
  });
  return counts;
};

export const filterByScoreRange = (items, min, max = Infinity) =>
  items.filter((item) => item.insight_score != null && item.insight_score >= min && item.insight_score < max);

export const ItemMetaLine = ({ item, source, now, corroborationLabel = 'also in' }) => (
  <div className="item-meta">
    <DomainBadge value={item.domain} />
    {item.category && <span className="tag">{item.category}</span>}
    <SourcePill source={source} />
    <span className="dot-sep">·</span>
    <span>{fmtAgo(item.published_at, now)}</span>
    {item.also_seen_in?.length > 0 && (
      <>
        <span className="dot-sep">·</span>
        <span className="also-seen">
          <span className="also-seen-dot" />
          {corroborationLabel} {item.also_seen_in.length}
        </span>
      </>
    )}
  </div>
);

// ---------- domain badge ----------
export const DomainBadge = ({ value }) => {
  if (!value) return null;
  const cls = value === 'security' ? 'solid-fail' : value === 'ai' ? 'solid-accent' : 'solid-mute';
  return <span className={`badge ${cls} dot`}>{value}</span>;
};

// ---------- run status badge ----------
export const RunStatus = ({ value }) => {
  const map = {
    running: ['solid-accent', 'running'],
    succeeded: ['solid-ok', 'succeeded'],
    partial: ['solid-warn', 'partial'],
    failed: ['solid-fail', 'failed'],
  };
  const [cls, label] = map[value] || ['solid-mute', value];
  return <span className={`badge ${cls} dot`}>{label}</span>;
};

// ---------- relative time ----------
export const fmtAgo = (iso, now) => {
  // Keep relative-time rendering centralized so cards and drawers stay consistent.
  if (!iso) return '—';
  const d = (now.getTime() - new Date(iso).getTime()) / 60000;
  if (d < 1) return 'just now';
  if (d < 60) return `${Math.round(d)}m ago`;
  if (d < 60 * 24) return `${Math.round(d / 60)}h ago`;
  return `${Math.round(d / 60 / 24)}d ago`;
};

export const fmtDur = (s) => {
  // Pipeline views use a compact duration format to avoid widening tables/cards.
  if (s < 60) return `${s.toFixed(1)}s`;
  if (s < 3600) return `${Math.round(s / 60)}m`;
  return `${(s / 3600).toFixed(1)}h`;
};

export const fmtTime = (iso) => {
  // Digest/run widgets display time-of-day only; date context is shown elsewhere.
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
};

// ---------- retention computation ----------
export const retentionFor = (score) => {
  // Mirror backend retention policy in one place for all score-driven UI labels.
  if (score == null) return { days: null, label: 'pending' };
  if (score < 10) return { days: 0, label: 'delete' };
  if (score < 30) return { days: 5, label: '5 days' };
  if (score < 50) return { days: 10, label: '10 days' };
  if (score < 75) return { days: 30, label: '30 days' };
  return { days: null, label: 'permanent' };
};
