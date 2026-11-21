// Usage: node record-perf.cjs <base> [runs]
// Times the Track Record view in fresh browser contexts: first contentful paint, time until the skeleton (or the
// old "Grading…" note) is on screen, time until the real numbers are on screen, and the /api/track-record request.
const { chromium } = require(process.env.PLAYWRIGHT_PATH || 'playwright');
const base = process.argv[2] || 'http://127.0.0.1:8766';
const runs = Number(process.argv[3] || 5);
const pctl = (xs, p) => { const s = [...xs].sort((a, b) => a - b); return s[Math.min(s.length - 1, Math.ceil(p * s.length) - 1)]; };
(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROMIUM_PATH || undefined });
  const rows = [];
  for (let i = 0; i < runs; i++) {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    const page = await ctx.newPage();
    const t0 = Date.now();
    await page.goto(base + '/#record', { waitUntil: 'commit' });
    const shell = await page.waitForFunction(() => document.querySelector('.record-hero, #view h1'), null, { timeout: 60000 }).then(() => Date.now() - t0).catch(() => null);
    const data = await page.waitForFunction(() => document.querySelector('.record-hero-stat strong.num') && document.querySelector('#sport-record .stat'), null, { timeout: 60000 })
      .then(() => Date.now() - t0).catch(() => null);
    const timing = await page.evaluate(() => {
      const fcp = performance.getEntriesByName('first-contentful-paint')[0];
      const api = performance.getEntriesByType('resource').find((r) => r.name.includes('/api/track-record'));
      return { fcp: fcp ? Math.round(fcp.startTime) : null, api: api ? Math.round(api.responseEnd - api.requestStart) : null, bytes: api ? api.transferSize : null };
    });
    rows.push({ run: i + 1, shell, data, ...timing });
    await ctx.close();
  }
  await browser.close();
  for (const r of rows) console.log(JSON.stringify(r));
  const keys = ['fcp', 'shell', 'data', 'api'];
  console.log(JSON.stringify(Object.fromEntries(keys.map((k) => [k, { median: pctl(rows.map((r) => r[k]).filter((x) => x != null), 0.5), p95: pctl(rows.map((r) => r[k]).filter((x) => x != null), 0.95) }]))));
})();
