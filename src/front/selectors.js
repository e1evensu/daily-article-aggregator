// Shared front-end selectors and chart helpers.
const countBy = (items, keyFn) => {
  const counts = {};
  items.forEach((item) => {
    const key = keyFn(item);
    if (key == null) return;
    counts[key] = (counts[key] || 0) + 1;
  });
  return counts;
};

  const scoreBuckets = [
    { label: '0–29', min: 0, max: 30 },
    { label: '30–49', min: 30, max: 50 },
    { label: '50–74', min: 50, max: 75 },
    { label: '75–89', min: 75, max: 90 },
    { label: '90–100', min: 90, max: 101 },
  ];

  const retentionRanges = [
    { label: 'permanent (≥75)', range: [75, 101], color: 'var(--accent)' },
    { label: '30 days (50–74)', range: [50, 75], color: 'var(--score-high)' },
    { label: '10 days (30–49)', range: [30, 50], color: 'var(--score-mid)' },
    { label: '5 days (10–29)', range: [10, 30], color: 'var(--score-low)' },
    { label: 'delete (<10)', range: [0, 10], color: 'var(--text-4)' },
  ];

export const safeRatio = (value, total) => {
  if (!total) return 0;
  return Math.max(0, Math.min(1, value / total));
};

export const getActiveRun = (runs) => {
  if (!Array.isArray(runs) || runs.length === 0) return null;
  return runs.find((run) => run.status === 'running') || runs[0];
};

export const summarizeSources = (sources) => ({
  approved: sources.filter((source) => source.status === 'approved').length,
  candidate: sources.filter((source) => source.status === 'candidate').length,
  good: sources.filter((source) => source.health === 'good').length,
  degraded: sources.filter((source) => source.health === 'degraded').length,
  disabled: sources.filter((source) => source.health === 'disabled').length,
  maxSpark: Math.max(1, ...sources.flatMap((source) => source.spark || [0])),
});

export const summarizeItems = (items) => ({
  all: items.length,
  security: items.filter((item) => item.domain === 'security').length,
  ai: items.filter((item) => item.domain === 'ai').length,
  highValue: items.filter((item) => (item.insight_score || 0) >= 75).length,
  confidence: {
    tentative: items.filter((item) => item.confidence === 'tentative').length,
    firm: items.filter((item) => item.confidence === 'firm').length,
    confirmed: items.filter((item) => item.confidence === 'confirmed').length,
  },
});

export const filterItems = (items, filters, tweaks) => {
  let filtered = items.slice();
  if (filters.domain !== 'all') filtered = filtered.filter((item) => item.domain === filters.domain);
  if (filters.minScore > 0) filtered = filtered.filter((item) => (item.insight_score || 0) >= filters.minScore);
  if (filters.query) {
    const query = filters.query.toLowerCase();
    filtered = filtered.filter(
      (item) => item.title.toLowerCase().includes(query) || (item.summary_zh || '').includes(filters.query),
    );
  }
  if (!tweaks.showLow) filtered = filtered.filter((item) => (item.insight_score || 0) >= 30);
  filtered.sort((left, right) => (right.insight_score || 0) - (left.insight_score || 0));
  return filtered;
};

export const scoreHistogram = (items) => {
  const buckets = Array(20).fill(0);
  items.forEach((item) => {
    if (item.insight_score == null) return;
    const bucket = Math.min(19, Math.floor(item.insight_score / 5));
    buckets[bucket] += 1;
  });
  return { buckets, max: Math.max(...buckets, 1) };
};

export const categoryScoreMatrix = (items) => {
    const categories = ['vulnerability', 'exploit', 'research', 'product', 'engineering', 'discussion', 'tool', 'incident'];
    const present = categories.filter((category) => items.some((item) => item.category === category));
    const counts = {};
    let max = 1;
    present.forEach((category) => {
      counts[category] = {};
      scoreBuckets.forEach((bucket) => {
        const count = items.filter(
          (item) => item.category === category && item.insight_score >= bucket.min && item.insight_score < bucket.max,
        ).length;
        counts[category][bucket.label] = count;
        max = Math.max(max, count);
      });
    });
    return { categories: present, buckets: scoreBuckets, counts, max };
};

export const categoryList = (items) => {
    const counts = countBy(items.filter((item) => item.category), (item) => item.category);
    const firstDomainByCategory = {};
    items.forEach((item) => {
      if (item.category && !firstDomainByCategory[item.category]) {
        firstDomainByCategory[item.category] = item.domain;
      }
    });
    const entries = Object.entries(counts)
      .map(([category, count]) => ({ category, count, domain: firstDomainByCategory[category] }))
      .sort((left, right) => right.count - left.count);
    return { entries, max: Math.max(...entries.map((entry) => entry.count), 1) };
};

export const retentionBuckets = (items) => retentionRanges.map((bucket) => {
    const count = items.filter(
      (item) => item.insight_score != null
        && item.insight_score >= bucket.range[0]
        && item.insight_score < bucket.range[1],
    ).length;
    return { ...bucket, count, ratio: safeRatio(count, items.length) };
});

export const modelUsage = (runs) => {
  const recent = runs.slice(0, 4).reverse();
  return {
    labels: recent.map((run) => new Date(run.started_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })),
    stage1: recent.map((run) => run.stats_json?.stage1?.succeeded || 0),
    stage2: recent.map((run) => run.stats_json?.stage2?.succeeded || 0),
  };
};
