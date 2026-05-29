// Digest reader / Runs monitor / Sources / Stats
const { useState: useStateV, useMemo: useMemoV } = React;

// ============ DIGEST ============
const DigestView = ({ digest, items, sources, now, onOpenItem }) => {
  const byId = (id) => items.find(i => i.id === id);
  return (
    <div className="view">
      <div className="digest-wrap">
        <div className="digest-hero">
          <div className="digest-date">{digest.date} · domain · security</div>
          <h1 className="digest-title">{digest.title}</h1>
          <p className="digest-overview">{digest.overview}</p>
          <div className="digest-stats">
            <div className="digest-stat">
              <div className="l">collected</div>
              <div className="v">{digest.stats.collected}</div>
            </div>
            <div className="digest-stat">
              <div className="l">analyzed</div>
              <div className="v">{digest.stats.analyzed}</div>
            </div>
            <div className="digest-stat">
              <div className="l">high-value</div>
              <div className="v" style={{ color: 'var(--accent)' }}>{digest.stats.high_value}</div>
            </div>
            <div className="digest-stat">
              <div className="l">failed sources</div>
              <div className="v" style={{ color: 'var(--fail)' }}>{digest.stats.failed_sources}</div>
            </div>
            <div className="digest-stat" style={{ marginLeft: 'auto', textAlign: 'right' }}>
              <div className="l">generated</div>
              <div className="v" style={{ fontSize: 13, fontWeight: 500 }}>{fmtAgo(digest.generated_at, now)}</div>
            </div>
          </div>
        </div>

        {digest.categories.map(cat => (
          <div key={cat.name} className="digest-cat">
            <div className="digest-cat-head">
              <span className="digest-cat-name">{cat.label}</span>
              <span className="digest-cat-count">{cat.count} · {cat.name}</span>
            </div>
            {cat.item_ids.map((id, idx) => {
              const it = byId(id); if (!it) return null;
              const src = sources.find(s => s.id === it.source_id);
              return (
                <div key={id} className="digest-item" onClick={() => onOpenItem(it)}>
                  <div className="digest-item-rank">0{idx + 1}</div>
                  <div>
                    <h4 className="digest-item-title">{it.title}</h4>
                    <p className="digest-item-summary">{it.summary_zh}</p>
                    <div className="digest-item-meta">
                      <ScoreNum value={it.insight_score} suffix="/100" />
                      <span className="dot-sep">·</span>
                      <SourcePill source={src} />
                      {it.also_seen_in?.length > 0 && (
                        <>
                          <span className="dot-sep">·</span>
                          <span className="also-seen">
                            <span className="also-seen-dot" />
                            corroborated by {it.also_seen_in.length}
                          </span>
                        </>
                      )}
                      <span style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
                        {it.analysis_stage === 2 && <Confidence value={it.confidence} />}
                        {it.trend_signal && <Trend value={it.trend_signal} />}
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        ))}

        <div className="digest-cat">
          <div className="digest-cat-head">
            <span className="digest-cat-name">Lower-value mentions</span>
            <span className="digest-cat-count">score 40–74 · summary only</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: '4px 0 0' }}>
            {items.filter(i => i.domain === 'security' && i.insight_score >= 40 && i.insight_score < 75).map(it => (
              <div key={it.id} style={{ display: 'grid', gridTemplateColumns: '40px 1fr auto', gap: 10, alignItems: 'center', padding: '6px 0', fontSize: 13 }} onClick={() => onOpenItem(it)}>
                <ScoreNum value={it.insight_score} />
                <span style={{ color: 'var(--text-2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{it.title}</span>
                <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text-3)' }}>{it.source_id}</span>
              </div>
            ))}
          </div>
        </div>

        <div style={{ marginTop: 40, paddingTop: 20, borderTop: '1px solid var(--border)', display: 'flex', gap: 12, alignItems: 'center', fontSize: 12, color: 'var(--text-3)', fontFamily: 'var(--mono)' }}>
          <Icon name="link" size={11} />
          <span>oss://intel-blog/2026/05/{digest.id}.md</span>
          <span style={{ marginLeft: 'auto' }}>id · {digest.id}</span>
        </div>
      </div>
    </div>
  );
};
window.DigestView = DigestView;

// ============ RUNS ============
const stepStatus = (run, key) => {
  const s = run.stats[key]; if (!s) return 'pending';
  if (s.failed > 0 && s.succeeded === 0) return 'fail';
  if (s.running > 0) return 'running';
  if (s.failed > 0) return 'warn';
  return 'ok';
};

const RunCard = ({ run, sources, now }) => {
  const ingest = run.stats.sources ? Object.values(run.stats.sources) : [];
  const ingested = ingest.reduce((a, b) => a + (b.items || 0), 0);
  const failedSrc = ingest.filter(s => s.status === 'failed').length;
  return (
    <div className="run-card">
      <div className="run-head">
        <RunStatus value={run.status} />
        <span className="run-id">{run.id}</span>
        <span className="tag">{run.kind}</span>
        <span style={{ color: 'var(--text-3)', fontSize: 12, fontFamily: 'var(--mono)' }}>
          started {fmtAgo(run.started_at, now)}
          {run.finished_at && <> · took {fmtDur((new Date(run.finished_at) - new Date(run.started_at)) / 1000)}</>}
        </span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          {run.status === 'running' && (
            <>
              <div style={{ width: 120, height: 4, background: 'var(--border)', borderRadius: 99, overflow: 'hidden' }}>
                <div style={{ width: (run.progress * 100) + '%', height: '100%', background: 'var(--accent)', transition: 'width .4s' }} />
              </div>
              <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--accent-text)' }}>{Math.round(run.progress * 100)}%</span>
            </>
          )}
        </div>
      </div>

      <div className="run-bar">
        <div className={`step ${failedSrc > 0 ? (failedSrc === ingest.length ? 'fail' : 'warn') : 'ok'}`}>
          <span className="step-name">FETCH</span>
          <span className="step-val">{ingest.length - failedSrc}/{ingest.length}</span>
        </div>
        <div className="step ok">
          <span className="step-name">NORMALIZE</span>
          <span className="step-val">{ingested}</span>
        </div>
        <div className="step ok">
          <span className="step-name">DEDUP</span>
          <span className="step-val">−{run.stats.dedup_skipped}</span>
        </div>
        <div className={`step ${run.stats.stage1.failed > 0 ? 'warn' : 'ok'}`}>
          <span className="step-name">STAGE 1</span>
          <span className="step-val">{run.stats.stage1.succeeded}/{run.stats.stage1.total}</span>
        </div>
        <div className={`step ${run.stats.stage2.running ? 'running' : 'ok'}`}>
          <span className="step-name">STAGE 2</span>
          <span className="step-val">
            {run.stats.stage2.succeeded}/{run.stats.stage2.total}
            {run.stats.stage2.running ? ` (+${run.stats.stage2.running})` : ''}
          </span>
        </div>
        <div className={`step ${run.status === 'running' ? '' : 'ok'}`}>
          <span className="step-name">DIGEST</span>
          <span className="step-val">{run.status === 'running' ? '—' : '✓'}</span>
        </div>
        <div className={`step ${run.status === 'running' ? '' : 'ok'}`}>
          <span className="step-name">CLEANUP</span>
          <span className="step-val">{run.status === 'running' ? '—' : `−${run.stats.retention_deleted}`}</span>
        </div>
      </div>

      {run.stats.sources && Object.keys(run.stats.sources).length > 0 && (
        <div className="run-sources-grid">
          {Object.entries(run.stats.sources).map(([id, s]) => {
            const src = sources.find(x => x.id === id);
            const cls = s.status === 'succeeded' ? 'ok' : s.status === 'failed' ? 'fail' : 'warn';
            return (
              <div key={id} className="run-source-row">
                <span className={`dot ${cls}`} />
                <span className="src-name">{src?.name || id}</span>
                <span className="src-items">{s.items != null ? `${s.items} items` : s.error}</span>
                <span className="src-dur">{fmtDur(s.duration_s)}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

const RunsView = ({ runs, sources, now }) => {
  const current = runs[0];
  const totalItems = current.stats.stage1.total;
  const failedItems = current.stats.stage1.failed;
  const stage2 = current.stats.stage2;
  return (
    <div className="runs-grid">
      <div className="stat-row">
        <div className="stat">
          <div className="stat-label">Active run</div>
          <div className="stat-value" style={{ color: 'var(--accent)' }}>{current.id.split('_').pop()}</div>
          <div className="stat-delta">started {fmtAgo(current.started_at, now)}</div>
        </div>
        <div className="stat">
          <div className="stat-label">Stage 1 progress</div>
          <div className="stat-value">{current.stats.stage1.succeeded}<span style={{ fontSize: 18, color: 'var(--text-3)' }}> / {totalItems}</span></div>
          <div className={`stat-delta ${failedItems > 0 ? 'down' : 'up'}`}>{failedItems} failed</div>
        </div>
        <div className="stat">
          <div className="stat-label">Stage 2 in flight</div>
          <div className="stat-value">{stage2.succeeded}<span style={{ fontSize: 18, color: 'var(--text-3)' }}> / {stage2.total}</span></div>
          <div className="stat-delta">{stage2.running || 0} running</div>
        </div>
        <div className="stat">
          <div className="stat-label">Concurrency lock</div>
          <div className="stat-value" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Icon name="lock" size={20} />
            <span style={{ fontSize: 18 }}>held</span>
          </div>
          <div className="stat-delta">12h stale timeout</div>
        </div>
      </div>

      {runs.map(r => <RunCard key={r.id} run={r} sources={sources} now={now} />)}
    </div>
  );
};
window.RunsView = RunsView;

// ============ SOURCES ============
const Spark = ({ data, max }) => {
  const m = max || Math.max(...data, 1);
  return (
    <div className="spark">
      {data.map((v, i) => (
        <div key={i} className={`sp-bar ${v === 0 ? 'fail' : ''}`} style={{ height: Math.max(2, (v / m) * 20) + 'px' }} />
      ))}
    </div>
  );
};

const SourcesView = ({ sources, items, now }) => {
  const counts = useMemoV(() => {
    const c = {};
    items.forEach(i => { c[i.source_id] = (c[i.source_id] || 0) + 1; });
    return c;
  }, [items]);
  const maxSpark = Math.max(...sources.flatMap(s => s.spark));
  return (
    <div>
      <div className="section-head">
        <div>
          <h1 className="section-title">Sources</h1>
          <div className="section-sub">10 approved sources · Phase 1 · L1 collectors only</div>
        </div>
        <div className="section-actions">
          <span className="badge solid-ok">{sources.filter(s => s.health === 'good').length} good</span>
          <span className="badge solid-warn">{sources.filter(s => s.health === 'degraded').length} degraded</span>
          <span className="badge solid-fail">{sources.filter(s => s.health === 'disabled').length} disabled</span>
        </div>
      </div>
      <div style={{ overflow: 'auto' }}>
        <table className="src-table">
          <thead>
            <tr>
              <th>Source</th>
              <th>Domain</th>
              <th>Type</th>
              <th>Authority</th>
              <th>Health</th>
              <th>14-day</th>
              <th style={{ textAlign: 'right' }}>Today</th>
              <th style={{ textAlign: 'right' }}>Last fetch</th>
            </tr>
          </thead>
          <tbody>
            {sources.map(s => (
              <tr key={s.id}>
                <td>
                  <div style={{ fontWeight: 500 }}>{s.name}</div>
                  <div className="src-id">{s.id}</div>
                </td>
                <td><DomainBadge value={s.domain} /></td>
                <td><span className="tag" style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                  <SourceIcon type={s.type} /> {s.type}
                </span></td>
                <td><span style={{ fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--text-2)' }}>{s.authority}</span></td>
                <td>
                  <Health value={s.health} />
                  {s.consecutive_failures > 0 && (
                    <div style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--warn)', marginTop: 2 }}>
                      {s.consecutive_failures} consec fail
                    </div>
                  )}
                </td>
                <td><Spark data={s.spark} max={maxSpark} /></td>
                <td style={{ textAlign: 'right', fontFamily: 'var(--mono)', fontVariantNumeric: 'tabular-nums' }}>
                  <span style={{ color: s.today_items === 0 ? 'var(--text-3)' : 'var(--text)' }}>{s.today_items}</span>
                </td>
                <td style={{ textAlign: 'right', fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--text-3)' }}>
                  {fmtAgo(s.last_fetch_at, now)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
window.SourcesView = SourcesView;

// ============ STATS ============
const Histogram = ({ items }) => {
  // 20 buckets of 5 each
  const buckets = Array(20).fill(0);
  items.forEach(i => {
    if (i.insight_score == null) return;
    const b = Math.min(19, Math.floor(i.insight_score / 5));
    buckets[b]++;
  });
  const max = Math.max(...buckets, 1);
  return (
    <div className="card">
      <h3 className="card-title">insight_score distribution · today</h3>
      <div className="hist" style={{ position: 'relative' }}>
        <div className="hist-threshold" style={{ left: '75%' }} />
        {buckets.map((v, i) => {
          const score = i * 5;
          const cls = score < 30 ? 'b-low' : score < 50 ? 'b-mid' : score < 75 ? 'b-high' : 'b-top';
          return (
            <div key={i} className={`hist-bar ${cls}`} style={{ height: (v / max) * 100 + '%' }}
              title={`${score}–${score + 5}: ${v} items`} />
          );
        })}
      </div>
      <div className="hist-axis">
        <span>0</span><span>25</span><span>50</span><span>75</span><span>100</span>
      </div>
      <div style={{ display: 'flex', gap: 20, marginTop: 14, paddingTop: 12, borderTop: '1px dashed var(--border)' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <span style={{ fontSize: 10, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>kept (≥30)</span>
          <span style={{ fontFamily: 'var(--mono)', fontSize: 20, fontWeight: 600 }}>{items.filter(i => i.insight_score >= 30).length}</span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <span style={{ fontSize: 10, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>stage 2 (≥75)</span>
          <span style={{ fontFamily: 'var(--mono)', fontSize: 20, fontWeight: 600, color: 'var(--accent)' }}>{items.filter(i => i.insight_score >= 75).length}</span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <span style={{ fontSize: 10, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>retention drop</span>
          <span style={{ fontFamily: 'var(--mono)', fontSize: 20, fontWeight: 600, color: 'var(--text-3)' }}>{items.filter(i => i.insight_score < 30).length}</span>
        </div>
        <div style={{ marginLeft: 'auto', alignSelf: 'flex-end', fontSize: 11, color: 'var(--text-3)', fontFamily: 'var(--mono)' }}>
          n = {items.length}
        </div>
      </div>
    </div>
  );
};

const CategoryByDomainMatrix = ({ items }) => {
  const cats = ['vulnerability', 'exploit', 'research', 'product', 'engineering', 'discussion', 'tool', 'incident'];
  const buckets = [
    { label: '0–29', test: s => s < 30 },
    { label: '30–49', test: s => s >= 30 && s < 50 },
    { label: '50–74', test: s => s >= 50 && s < 75 },
    { label: '75–89', test: s => s >= 75 && s < 90 },
    { label: '90–100', test: s => s >= 90 },
  ];
  const present = cats.filter(c => items.some(i => i.category === c));
  const max = Math.max(1, ...present.flatMap(c => buckets.map(b => items.filter(i => i.category === c && b.test(i.insight_score)).length)));
  return (
    <div className="card">
      <h3 className="card-title">category × insight_score</h3>
      <div className="matrix">
        <div className="mh"></div>
        {buckets.map(b => <div key={b.label} className="mh">{b.label}</div>)}
        {present.map(cat => (
          <React.Fragment key={cat}>
            <div className="mh row">{cat}</div>
            {buckets.map(b => {
              const n = items.filter(i => i.category === cat && b.test(i.insight_score)).length;
              const intensity = n / max;
              const isTop = b.label.startsWith('75') || b.label.startsWith('90');
              const bg = n === 0 ? 'var(--panel-2)' :
                isTop ? `color-mix(in oklab, var(--accent) ${10 + intensity * 70}%, var(--panel))` :
                  `color-mix(in oklab, var(--text-2) ${5 + intensity * 30}%, var(--panel))`;
              const color = n > 0 && intensity > 0.5 && isTop ? 'white' : 'var(--text)';
              return <div key={cat + b.label} className="mc" style={{ background: bg, color }}>{n || ''}</div>;
            })}
          </React.Fragment>
        ))}
      </div>
    </div>
  );
};

const CategoryList = ({ items }) => {
  const map = {};
  items.forEach(i => {
    if (!i.category) return;
    if (!map[i.category]) map[i.category] = { count: 0, domain: i.domain };
    map[i.category].count++;
  });
  const arr = Object.entries(map).sort((a, b) => b[1].count - a[1].count);
  const max = Math.max(...arr.map(([, v]) => v.count), 1);
  return (
    <div className="card">
      <h3 className="card-title">by category</h3>
      <div className="cat-list">
        {arr.map(([name, v]) => (
          <div key={name} className="cat-row">
            <div className="cat-name">
              <span>{name}</span>
            </div>
            <div className="cat-bar">
              <div className={`cat-bar-fill ${v.domain}`} style={{ width: (v.count / max * 100) + '%' }} />
            </div>
            <div className="cat-count">{v.count}</div>
          </div>
        ))}
      </div>
    </div>
  );
};

const StatsView = ({ items, runs, sources, now }) => {
  const high = items.filter(i => i.insight_score >= 75);
  const conf = {
    tentative: items.filter(i => i.confidence === 'tentative').length,
    firm: items.filter(i => i.confidence === 'firm').length,
    confirmed: items.filter(i => i.confidence === 'confirmed').length,
  };
  return (
    <div className="stats-wrap">
      <div className="stat-row" style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14 }}>
        <div className="stat">
          <div className="stat-label">Items today</div>
          <div className="stat-value">{items.length}</div>
          <div className="stat-delta up">+12 vs yesterday</div>
        </div>
        <div className="stat">
          <div className="stat-label">High-value (≥75)</div>
          <div className="stat-value" style={{ color: 'var(--accent)' }}>{high.length}</div>
          <div className="stat-delta">stage 2 analyzed</div>
        </div>
        <div className="stat">
          <div className="stat-label">Failed analyses</div>
          <div className="stat-value">{runs[0].stats.stage1.failed}</div>
          <div className="stat-delta down">{runs[0].stats.stage1.failed} model_parse_error</div>
        </div>
        <div className="stat">
          <div className="stat-label">Sources healthy</div>
          <div className="stat-value">{sources.filter(s => s.health === 'good').length}<span style={{ fontSize: 18, color: 'var(--text-3)' }}> / {sources.length}</span></div>
          <div className="stat-delta down">1 degraded</div>
        </div>
      </div>

      <Histogram items={items} />

      <div className="stats-row-3">
        <CategoryByDomainMatrix items={items} />
        <CategoryList items={items} />
      </div>

      <div className="stats-row-2">
        <div className="card">
          <h3 className="card-title">confidence breakdown · stage 2</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 6 }}>
            {['tentative', 'firm', 'confirmed'].map(c => {
              const n = conf[c]; const total = conf.tentative + conf.firm + conf.confirmed || 1;
              return (
                <div key={c} style={{ display: 'grid', gridTemplateColumns: '110px 1fr 40px', gap: 10, alignItems: 'center' }}>
                  <Confidence value={c} />
                  <div className="cat-bar">
                    <div className="cat-bar-fill" style={{ width: (n / total * 100) + '%', background: c === 'confirmed' ? 'var(--accent)' : 'var(--text-2)' }} />
                  </div>
                  <span style={{ textAlign: 'right', fontFamily: 'var(--mono)', fontVariantNumeric: 'tabular-nums' }}>{n}</span>
                </div>
              );
            })}
          </div>
          <div style={{ marginTop: 14, paddingTop: 12, borderTop: '1px dashed var(--border)', fontSize: 12, color: 'var(--text-3)' }}>
            <div style={{ marginBottom: 4 }}>· <code style={{ fontFamily: 'var(--mono)' }}>firm</code> when source authority is <code style={{ fontFamily: 'var(--mono)' }}>official</code> or ≥1 corroborating source.</div>
            <div>· <code style={{ fontFamily: 'var(--mono)' }}>confirmed</code> when official + corroborated, or ≥2 corroborating sources.</div>
          </div>
        </div>

        <div className="card">
          <h3 className="card-title">retention buckets</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {[
              { label: 'permanent (≥75)', range: [75, 101], color: 'var(--accent)' },
              { label: '30 days (50–74)', range: [50, 75], color: 'var(--score-high)' },
              { label: '10 days (30–49)', range: [30, 50], color: 'var(--score-mid)' },
              { label: '5 days (10–29)', range: [10, 30], color: 'var(--score-low)' },
              { label: 'delete (<10)', range: [0, 10], color: 'var(--text-4)' },
            ].map(r => {
              const n = items.filter(i => i.insight_score >= r.range[0] && i.insight_score < r.range[1]).length;
              return (
                <div key={r.label} style={{ display: 'grid', gridTemplateColumns: '160px 1fr 40px', gap: 10, alignItems: 'center', fontSize: 13 }}>
                  <span style={{ color: 'var(--text-2)' }}>{r.label}</span>
                  <div className="cat-bar">
                    <div className="cat-bar-fill" style={{ width: (n / items.length * 100) + '%', background: r.color }} />
                  </div>
                  <span style={{ textAlign: 'right', fontFamily: 'var(--mono)', fontVariantNumeric: 'tabular-nums' }}>{n}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      <div className="card">
        <h3 className="card-title">model usage · last 4 runs</h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 20 }}>
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 6 }}>
              <span style={{ fontFamily: 'var(--mono)', fontSize: 13 }}>deepseek-v4-flash</span>
              <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text-3)' }}>stage 1 · nvidia</span>
            </div>
            <div className="timeline">
              {[48, 54, 47, 63].map((v, i) => (
                <div key={i} className="timeline-bar">
                  <div className="tb-stack s1" style={{ height: (v / 70 * 100) + '%' }} />
                </div>
              ))}
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 6, fontSize: 11, fontFamily: 'var(--mono)', color: 'var(--text-3)' }}>
              <span>May 23</span><span>May 24</span><span>May 25</span><span>May 26</span>
            </div>
          </div>
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 6 }}>
              <span style={{ fontFamily: 'var(--mono)', fontSize: 13 }}>deepseek-v4-pro</span>
              <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text-3)' }}>stage 2 · nvidia</span>
            </div>
            <div className="timeline">
              {[2, 8, 7, 9].map((v, i) => (
                <div key={i} className="timeline-bar">
                  <div className="tb-stack" style={{ height: (v / 12 * 100) + '%' }} />
                </div>
              ))}
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 6, fontSize: 11, fontFamily: 'var(--mono)', color: 'var(--text-3)' }}>
              <span>May 23</span><span>May 24</span><span>May 25</span><span>May 26</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
window.StatsView = StatsView;
