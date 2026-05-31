// Items list + detail drawer
const { useState: useStateI, useMemo: useMemoI, useEffect: useEffectI } = React;
import {
  Confidence,
  Credibility,
  DomainBadge,
  Icon,
  ItemMetaLine,
  ScoreBar,
  ScoreNum,
  SourceIcon,
  SourcePill,
  Trend,
  fmtAgo,
  retentionFor,
  scoreClass,
} from './ui.jsx';
import { filterItems, summarizeItems } from './selectors.js';

const ItemRow = ({ item, source, selected, onClick, now }) => {
  const score = item.insight_score;
  return (
    <div className={`item-row ${selected ? 'selected' : ''}`} onClick={onClick}>
      <div className="item-score">
        <ScoreNum value={score} />
        <ScoreBar value={score} />
      </div>
      <div className="item-body">
        <h3 className="item-title">{item.title}</h3>
        {item.summary_zh && <p className="item-summary">{item.summary_zh}</p>}
        <ItemMetaLine item={item} source={source} now={now} />
      </div>
      <div className="item-side">
        {item.analysis_stage === 2 && <Confidence value={item.confidence} />}
        {item.analysis_stage === 2 && item.trend_signal && <Trend value={item.trend_signal} />}
        {item.analysis_stage === 1 && score < 75 && (
          <span className="badge" title="Stage 2 skipped: score < 75">stage 1 only</span>
        )}
      </div>
    </div>
  );
};

const ItemDrawer = ({ item, source, onClose, sourceById, now }) => {
  if (!item) return null;
  const ret = retentionFor(item.insight_score);
  const alsoIn = (item.also_seen_in || [])
    .map(o => ({ occurrence: o, source: sourceById[o.source_id] }))
    .filter(x => x.source);
  return (
    <>
      <div className={`drawer-mask ${item ? 'open' : ''}`} onClick={onClose} />
      <div className={`drawer ${item ? 'open' : ''}`} onClick={(e) => e.stopPropagation()}>
        <div className="drawer-head">
          <DomainBadge value={item.domain} />
          {item.category && <span className="tag">{item.category}</span>}
          <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text-3)', marginLeft: 8 }}>
            {item.id}
          </span>
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
            <a className="btn sm" href={item.canonical_url} target="_blank" rel="noreferrer">
              <Icon name="ext" size={12} />
              source
            </a>
            <button className="icon-btn" onClick={onClose} title="Close">
              <Icon name="x" size={14} />
            </button>
          </div>
        </div>
        <div className="drawer-body">
          <h2>{item.title}</h2>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 20, flexWrap: 'wrap' }}>
            <SourcePill source={source} />
            <span style={{ color: 'var(--text-3)', fontSize: 12 }}>·</span>
            <span style={{ color: 'var(--text-2)', fontSize: 13 }}>{item.author}</span>
            <span style={{ color: 'var(--text-3)', fontSize: 12 }}>·</span>
            <span style={{ color: 'var(--text-2)', fontSize: 13 }}>published {fmtAgo(item.published_at, now)}</span>
            <span style={{ color: 'var(--text-3)', fontSize: 12 }}>·</span>
            <span style={{ color: 'var(--text-2)', fontSize: 13 }}>fetched {fmtAgo(item.fetched_at, now)}</span>
          </div>

          {/* score block */}
          <div className="card" style={{ marginBottom: 18 }}>
            <h3 className="card-title">insight_score</h3>
            <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
              <div className={`score-num ${scoreClass(item.insight_score)}`} style={{ fontSize: 36, lineHeight: 1 }}>
                {item.insight_score}<span className="pct" style={{ fontSize: 14 }}>/100</span>
              </div>
              <div style={{ flex: 1 }}>
                <ScoreBar value={item.insight_score} />
                <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 6, fontSize: 10, color: 'var(--text-3)', fontFamily: 'var(--mono)' }}>
                  <span>0</span><span>30</span><span>50</span><span style={{ color: 'var(--text-2)' }}>75 ▲ stage 2</span><span>100</span>
                </div>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
                <Credibility value={item.credibility} />
                <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text-3)' }}>
                  retention: {ret.label}
                </span>
              </div>
            </div>
          </div>

          {/* Stage 1 */}
          <div className="stage-panel">
            <div className="stage-head">
              <span className="stage-num">STAGE 1</span>
              <span className="stage-title">Triage · classification & summary</span>
              <div className="stage-meta">
                <span>{item.stage1_model}</span>
                <span>·</span>
                <span>{item.stage1_prompt_version}</span>
              </div>
            </div>
            <div className="stage-body">
              <div className="label">summary_zh</div>
              <p>{item.summary_zh}</p>
              <div className="label">tags</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                {(item.tags || []).map(t => <span key={t} className="tag">{t}</span>)}
              </div>
              {item.cve_id && (
                <>
                  <div className="label">CVE detail</div>
                  <div className="kv"><span className="k">cve_id</span><span className="v mono">{item.cve_id}</span></div>
                  {item.cvss && <div className="kv"><span className="k">cvss</span><span className="v mono">{item.cvss}</span></div>}
                  {item.cvss_vector && <div className="kv"><span className="k">vector</span><span className="v mono">{item.cvss_vector}</span></div>}
                </>
              )}
            </div>
          </div>

          {/* Stage 2 */}
          {item.analysis_stage === 2 ? (
            <div className="stage-panel s2">
              <div className="stage-head">
                <span className="stage-num">STAGE 2</span>
                <span className="stage-title">Deep analysis · score ≥ 75</span>
                <div className="stage-meta">
                  <span>{item.stage2_model}</span><span>·</span><span>{item.stage2_prompt_version}</span>
                </div>
              </div>
              <div className="stage-body">
                <div className="label">confidence</div>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                  <Confidence value={item.confidence} />
                  {item.trend_signal && <Trend value={item.trend_signal} />}
                </div>
                <div className="label">recommendation_reason</div>
                <p>{item.recommendation_reason}</p>
                <div className="label">action_suggestion</div>
                <p>{item.action_suggestion}</p>
              </div>
            </div>
          ) : (
            <div className="stage-panel">
              <div className="stage-head">
                <span className="stage-num">STAGE 2</span>
                <span className="stage-title">Not triggered</span>
              </div>
              <div className="stage-locked">
                <Icon name="lock" size={16} />
                <div style={{ marginTop: 8 }}>
                  Stage 2 runs only when insight_score ≥ 75.
                  <br/>
                  This item scored <b>{item.insight_score}</b> — below threshold.
                </div>
                <div className="lock-bar"><ScoreBar value={item.insight_score} /></div>
              </div>
            </div>
          )}

          {/* cross-source */}
          {alsoIn.length > 0 && (
            <>
              <h3>cross-source · also_seen_in</h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {alsoIn.map(({ occurrence, source: s }) => (
                  <div key={`${s.id}-${occurrence.url || occurrence.seen_at}`} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '7px 10px', background: 'var(--panel-2)', borderRadius: 6 }}>
                    <SourceIcon type={s.type} />
                    <span style={{ fontSize: 13 }}>{s.name}</span>
                    {occurrence.url && <a className="tag" href={occurrence.url} target="_blank" rel="noreferrer">url</a>}
                    <span style={{ marginLeft: 'auto', fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text-3)' }}>{fmtAgo(occurrence.seen_at, now)}</span>
                  </div>
                ))}
              </div>
            </>
          )}

          {/* metadata */}
          <h3>analysis metadata</h3>
          <div className="kv"><span className="k">analysis_stage</span><span className="v mono">{item.analysis_stage}</span></div>
          <div className="kv"><span className="k">stage1_model</span><span className="v mono">{item.stage1_model}</span></div>
          <div className="kv"><span className="k">stage1_provider</span><span className="v mono">{item.stage1_provider}</span></div>
          <div className="kv"><span className="k">stage1_prompt_version</span><span className="v mono">{item.stage1_prompt_version}</span></div>
          <div className="kv"><span className="k">stage1_analyzed_at</span><span className="v mono">{fmtAgo(item.stage1_analyzed_at, now)}</span></div>
          {item.analysis_stage === 2 && (
            <>
              <div className="kv"><span className="k">stage2_model</span><span className="v mono">{item.stage2_model}</span></div>
              <div className="kv"><span className="k">stage2_provider</span><span className="v mono">{item.stage2_provider}</span></div>
              <div className="kv"><span className="k">stage2_prompt_version</span><span className="v mono">{item.stage2_prompt_version}</span></div>
              <div className="kv"><span className="k">stage2_analyzed_at</span><span className="v mono">{fmtAgo(item.stage2_analyzed_at, now)}</span></div>
            </>
          )}
          <div className="kv"><span className="k">expires_at</span><span className="v mono">{ret.label}</span></div>
          <div className="kv"><span className="k">dedup_hash</span><span className="v mono">{item.id}</span></div>
        </div>
      </div>
    </>
  );
};

export const ItemsView = ({ items, sources, now, tweaks }) => {
  const [filters, setFilters] = useStateI({ domain: 'all', minScore: 0, query: '' });
  const [sel, setSel] = useStateI(null);
  const sourceById = useMemoI(
    () => Object.fromEntries(sources.map((source) => [source.id, source])),
    [sources],
  );
  const counts = useMemoI(() => summarizeItems(items), [items]);

  const filtered = useMemoI(() => {
    return filterItems(items, filters, tweaks);
  }, [items, filters, tweaks]);

  return (
    <>
      <div className="section-head">
        <div>
          <h1 className="section-title">Items</h1>
          <div className="section-sub">
            Normalized intelligence items with inline analysis · ordered by insight_score
          </div>
        </div>
        <div className="section-actions">
          <button className="btn">
            <Icon name="refresh" size={13} />
            Refresh
          </button>
        </div>
      </div>

      <div className="toolbar">
        <button className={`chip ${filters.domain === 'all' ? 'active' : ''}`} onClick={() => setFilters({ ...filters, domain: 'all' })}>
          All <span className="count">{counts.all}</span>
        </button>
        <button className={`chip ${filters.domain === 'security' ? 'active' : ''}`} onClick={() => setFilters({ ...filters, domain: 'security' })}>
          Security <span className="count">{counts.security}</span>
        </button>
        <button className={`chip ${filters.domain === 'ai' ? 'active' : ''}`} onClick={() => setFilters({ ...filters, domain: 'ai' })}>
          AI <span className="count">{counts.ai}</span>
        </button>
        <div className="divider-y" />
        <span style={{ fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: 0 }}>min_score</span>
        <select className="select" value={filters.minScore} onChange={(e) => setFilters({ ...filters, minScore: +e.target.value })}>
          <option value={0}>any</option>
          <option value={30}>≥ 30 (kept)</option>
          <option value={50}>≥ 50</option>
          <option value={75}>≥ 75 (stage 2)</option>
        </select>
        <div className="toolbar-spacer" />
        <span style={{ fontSize: 12, color: 'var(--text-3)', fontFamily: 'var(--mono)' }}>
          {filtered.length} / {items.length} items
        </span>
      </div>

      <div>
        {filtered.length === 0 && <div className="empty">No items match these filters.</div>}
        {filtered.map(item => (
          <ItemRow
            key={item.id}
            item={item}
            source={sourceById[item.source_id]}
            selected={sel?.id === item.id}
            onClick={() => setSel(item)}
            now={now}
          />
        ))}
      </div>

      <ItemDrawer item={sel} source={sel && sourceById[sel.source_id]} onClose={() => setSel(null)} sourceById={sourceById} now={now} />
    </>
  );
};
