import { chromium } from "playwright";
import path from "path";
import { fileURLToPath } from "url";
import fs from "fs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const screenshotsDir = path.resolve(__dirname, "../docs/screenshots");

if (!fs.existsSync(screenshotsDir)) {
  fs.mkdirSync(screenshotsDir, { recursive: true });
}

async function run() {
  console.log("Starting visual verification and screenshot capture...");
  const browser = await chromium.launch({ headless: true });
  const baseURL = "http://localhost:3001";

  // Check widths: 360, 390, 430, 768, 1024, 1440
  const widths = [360, 390, 430, 768, 1024, 1440];

  for (const width of widths) {
    const page = await browser.newPage({
      viewport: { width, height: 900 },
      deviceScaleFactor: 2,
    });

    console.log(`Checking viewport ${width}px...`);
    await page.goto(baseURL, { waitUntil: "networkidle" });
    await page.waitForTimeout(600);

    // Verify no horizontal overflow
    const hasOverflow = await page.evaluate(() => {
      return document.documentElement.scrollWidth > window.innerWidth;
    });

    if (hasOverflow) {
      console.error(`FAILED: Horizontal document overflow detected at ${width}px!`);
    } else {
      console.log(`PASSED: No horizontal overflow at ${width}px (scrollWidth <= ${width}px)`);
    }

    await page.close();
  }

  // Capture Required Screenshots for each section in both Light and Dark themes
  const targets = [
    { name: "world-desktop-1440px-light", width: 1440, height: 900, theme: "light", tab: "WORLD" },
    { name: "world-desktop-1440px-dark", width: 1440, height: 900, theme: "dark", tab: "WORLD" },
    { name: "world-mobile-390px-light", width: 390, height: 844, theme: "light", tab: "WORLD" },
    { name: "world-mobile-390px-dark", width: 390, height: 844, theme: "dark", tab: "WORLD" },

    { name: "f1-desktop-1440px-light", width: 1440, height: 900, theme: "light", tab: "FORMULA 1" },
    { name: "f1-desktop-1440px-dark", width: 1440, height: 900, theme: "dark", tab: "FORMULA 1" },
    { name: "f1-mobile-390px-light", width: 390, height: 844, theme: "light", tab: "FORMULA 1" },
    { name: "f1-mobile-390px-dark", width: 390, height: 844, theme: "dark", tab: "FORMULA 1" },

    { name: "matches-desktop-1440px-light", width: 1440, height: 900, theme: "light", tab: "MATCHES" },
    { name: "matches-desktop-1440px-dark", width: 1440, height: 900, theme: "dark", tab: "MATCHES" },
    { name: "matches-mobile-390px-light", width: 390, height: 844, theme: "light", tab: "MATCHES" },
    { name: "matches-mobile-390px-dark", width: 390, height: 844, theme: "dark", tab: "MATCHES" },
  ];

  for (const t of targets) {
    const page = await browser.newPage({
      viewport: { width: t.width, height: t.height },
      deviceScaleFactor: 2,
    });

    await page.goto(baseURL, { waitUntil: "networkidle" });
    await page.waitForTimeout(500);

    // Set Theme
    await page.evaluate((themeMode) => {
      document.documentElement.setAttribute("data-theme", themeMode);
    }, t.theme);
    await page.waitForTimeout(200);

    // Select Tab (only visible buttons)
    if (t.tab !== "WORLD") {
      const tabButton = page.locator(`button:visible:has-text("${t.tab}")`).first();
      await tabButton.click();
      await page.waitForTimeout(500);
    }

    const filePath = path.join(screenshotsDir, `${t.name}.png`);
    await page.screenshot({ path: filePath, fullPage: false });
    console.log(`Saved screenshot: ${t.name}.png`);

    await page.close();
  }

  await browser.close();
  console.log("All visual inspections and screenshots completed successfully!");
}

run().catch((err) => {
  console.error("Screenshot capture error:", err);
  process.exit(1);
});
