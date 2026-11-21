// Usage: node capture.cjs <outDir> <base> [prefix]
// Screenshots of the root route, every dashboard view, one match detail and /lab at 360, 768, 1280 and 1920 px,
// plus console errors, CSP violations and failed requests per page. `prefix` is the path that serves dash.html
// ("/" locally; "/dash" on a host whose root serves something else). Read-only: it never presses buttons that write.
const { chromium } = require(process.env.PLAYWRIGHT_PATH || 'playwright');
const fs = require('fs');
const path = require('path');
const [out, base, prefix = '/', matchId = 'tennis-187528'] = process.argv.slice(2);
fs.mkdirSync(out, { recursive: true });
const WIDTHS = [[360, 800], [768, 1024], [1280, 900], [1920, 1080]];
const PAGES = [['root', '/'], ['matches', `${prefix}#matches`], ['match', `${prefix}#match/${matchId}`], ['world', `${prefix}#world`],
  ['f1', `${prefix}#f1`], ['record', `${prefix}#record`], ['settings', `${prefix}#settings`], ['lab', '/lab']];
(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROMIUM_PATH || undefined });
  const log = [];
  for (const [w, h] of WIDTHS) {
    // One context per width: a host's bot check (Vercel's checkpoint) is passed once and its cookie reused.
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, reducedMotion: 'reduce' });
    for (const [name, url] of PAGES) {
      const page = await ctx.newPage();
      const errors = [], failed = [], api = [];
      page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
      page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
      page.on('requestfailed', (r) => failed.push(`${r.url()} ${r.failure()?.errorText}`));
      page.on('response', (r) => { if (r.url().includes('/api/')) api.push(`${r.status()} ${new URL(r.url()).pathname}`); });
      const t0 = Date.now();
      await page.goto(base + url, { waitUntil: 'domcontentloaded' }).catch((e) => errors.push('goto: ' + e.message));
      if (/Security Checkpoint/.test(await page.title().catch(() => ''))) { await page.waitForTimeout(8000); await page.goto(base + url, { waitUntil: 'domcontentloaded' }).catch(() => {}); }
      await page.waitForTimeout(name === 'match' ? 9000 : ['world', 'f1', 'record'].includes(name) ? 6000 : 3000);
      await page.evaluate(() => document.fonts && document.fonts.ready).catch(() => {});
      const info = await page.evaluate(() => ({ title: document.title, h1: (document.querySelector('h1') || {}).textContent || '',
        sw: document.documentElement.scrollWidth, iw: innerWidth, html: document.documentElement.outerHTML.length,
        dash: !!document.getElementById('view') })).catch(() => ({}));
      const file = path.join(out, `${name}-${w}.png`);
      await page.screenshot({ path: file, fullPage: true }).catch(() => {});
      log.push({ page: name, url, w, ms: Date.now() - t0, title: info.title, h1: (info.h1 || '').replace(/\s+/g, ' ').trim().slice(0, 80),
        dashboard: info.dash, overflowX: info.sw > info.iw, api: [...new Set(api)], errors: errors.slice(0, 8), failed: failed.slice(0, 8), file });
      await page.close();
    }
    await ctx.close();
  }
  await browser.close();
  fs.writeFileSync(path.join(out, 'log.json'), JSON.stringify(log, null, 1));
  console.log(`${log.length} pages captured into ${out}`);
})();
