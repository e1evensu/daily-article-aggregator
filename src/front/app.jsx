// App shell — sidebar + topbar + view router + tweaks
const { useState: useStateApp, useEffect: useEffectApp, useMemo: useMemoApp } = React;
import { FIXTURES } from './data.js';
import { getActiveRun, safeRatio, summarizeSources } from './selectors.js';
import { Icon, fmtAgo } from './ui.jsx';
import { ItemsView } from './view-items.jsx';
import { DigestView, RunsView, SourcesView, StatsView } from './view-other.jsx';
import { TweaksPanel, TweakRadio, TweakSection, TweakToggle, useTweaks } from './tweaks-panel.jsx';

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "theme": "light",
  "showLow": true,
  "compact": false
}/*EDITMODE-END*/;

const NAV = [
  { id: 'items', label: 'Items', icon: 'inbox' },
  { id: 'digest', label: 'Digest', icon: 'newspaper' },
  { id: 'runs', label: 'Runs', icon: 'activity' },
  { id: 'sources', label: 'Sources', icon: 'database' },
  { id: 'stats', label: 'Stats', icon: 'bar' },
];
const NAV_BY_ID = Object.fromEntries(NAV.map((item) => [item.id, item]));

// Root shell that wires fixtures, top-level navigation, and tweak controls together.
export function App() {
  // Root shell that routes between the prototype's major intelligence surfaces.
  const [view, setView] = useStateApp('items');
  const [tweaks, setTweak] = useTweaks(TWEAK_DEFAULTS);
  const { now, sources, items, runs, digest } = FIXTURES;

  // theme
  useEffectApp(() => {
    document.documentElement.setAttribute('data-theme', tweaks.theme || 'light');
  }, [tweaks.theme]);

  const activeRun = getActiveRun(runs);
  const sourceSummary = useMemoApp(() => summarizeSources(sources), [sources]);
  const counts = useMemoApp(() => ({
    items: items.length,
    digest: digest ? 1 : 0,
    runs: runs.filter(r => r.status === 'running').length || runs.length,
    sources: sources.length,
  }), [digest, items, runs, sources]);

  const openItem = (it) => {
    // Jump to the items view first, then notify the drawer listener which item to open.
    setView('items');
    setTimeout(() => {
      const ev = new CustomEvent('open-item', { detail: it.id });
      window.dispatchEvent(ev);
    }, 50);
  };

  return (
    <div className="app">
      {/* SIDEBAR */}
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-logo">i</div>
          <div className="brand-name">intel</div>
          <span className="brand-env">phase 1</span>
        </div>

        <div className="nav-section-label">Surfaces</div>
        {NAV.map(n => (
          <div key={n.id} className={`nav-item ${view === n.id ? 'active' : ''}`} onClick={() => setView(n.id)}>
            <Icon name={n.icon} size={14} className="nav-icon" />
            <span>{n.label}</span>
            {n.id === 'runs' && activeRun?.status === 'running'
              ? <span className="nav-dot running" />
              : n.id === 'sources' && sourceSummary.degraded > 0
                ? <span className="nav-dot warn" />
                : <span className="nav-count">{
                  n.id === 'items' ? counts.items :
                    n.id === 'runs' ? runs.length :
                      n.id === 'sources' ? counts.sources :
                        n.id === 'stats' ? '' :
                          '1/d'
                }</span>}
          </div>
        ))}

        <div className="nav-section-label">Pipeline</div>
        <div className="nav-item">
          <span className="dot ok" style={{ marginLeft: 2 }} />
          <span>MySQL 8 · 114</span>
        </div>
        <div className="nav-item">
          <span className="dot ok" style={{ marginLeft: 2 }} />
          <span>Redis · 114</span>
        </div>
        <div className="nav-item">
          <span className="dot ok" style={{ marginLeft: 2 }} />
          <span>NVIDIA NIM</span>
        </div>
        <div className="nav-item">
          <span className="dot warn" style={{ marginLeft: 2 }} />
          <span>OSS</span>
          <span className="nav-count">retry</span>
        </div>

        <div className="sidebar-foot">
          <div className="run-banner">
            <div className="run-banner-head">
              <span className={`dot ${activeRun?.status === 'running' ? 'running' : 'warn'}`} />
              <span>{activeRun ? 'Active run' : 'Run queue'}</span>
              {activeRun && (
                <span style={{ marginLeft: 'auto', fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text-3)' }}>
                  {Math.round(activeRun.progress * 100)}%
                </span>
              )}
            </div>
            <div className="run-progress">
              <div className="run-progress-fill" style={{ width: `${safeRatio(activeRun?.progress || 0, 1) * 100}%` }} />
            </div>
            <div className="run-banner-meta">
              {activeRun ? (
                <>
                  <span>{activeRun.id.split('_').pop()}</span>
                  <span>started {fmtAgo(activeRun.started_at, now)}</span>
                </>
              ) : (
                <>
                  <span>no runs</span>
                  <span>waiting for first pipeline execution</span>
                </>
              )}
            </div>
          </div>
          <button className="nav-item" style={{ width: '100%' }}
            onClick={() => setTweak('theme', tweaks.theme === 'light' ? 'dark' : 'light')}>
            <Icon name={tweaks.theme === 'light' ? 'moon' : 'sun'} size={14} className="nav-icon" />
            <span>{tweaks.theme === 'light' ? 'Dark mode' : 'Light mode'}</span>
            <span className="kbd">T</span>
          </button>
        </div>
      </aside>

      {/* MAIN */}
      <main className="main">
        <div className="topbar">
          <div className="crumbs">
            <span>intel</span>
            <span className="sep">/</span>
            <span className="here">{NAV_BY_ID[view]?.label}</span>
          </div>
          <div className="topbar-right">
            <div className="search-box">
              <Icon name="search" size={13} />
              <input placeholder="Search items, sources, runs…" />
              <span className="kbd">⌘K</span>
            </div>
            <button className="icon-btn" title="Trigger manual run" onClick={() => alert('POST /api/v1/runs would be a Phase 2 endpoint — manual trigger here is illustrative.')}>
              <Icon name="play" size={13} />
            </button>
            <button className="icon-btn primary" title="Refresh">
              <Icon name="refresh" size={13} />
            </button>
          </div>
        </div>

        <div className="view" key={view}>
          {view === 'items' && <ItemsView items={items} sources={sources} now={now} tweaks={tweaks} />}
          {view === 'digest' && <DigestView digest={digest} items={items} sources={sources} now={now} onOpenItem={openItem} />}
          {view === 'runs' && <RunsView runs={runs} sources={sources} now={now} />}
          {view === 'sources' && <SourcesView sources={sources} items={items} now={now} />}
          {view === 'stats' && <StatsView items={items} runs={runs} sources={sources} now={now} />}
        </div>
      </main>

      {/* TWEAKS */}
      <TweaksPanel>
        <TweakSection label="Appearance" />
        <TweakRadio label="Theme" value={tweaks.theme} options={['light', 'dark']} onChange={(v) => setTweak('theme', v)} />
        <TweakSection label="Items view" />
        <TweakToggle label="Show score < 30" value={tweaks.showLow} onChange={(v) => setTweak('showLow', v)} />
        <TweakSection label="Layout" />
        <TweakToggle label="Compact rows" value={tweaks.compact} onChange={(v) => setTweak('compact', v)} />
      </TweaksPanel>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
