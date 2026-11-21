import { mkdirSync } from 'node:fs';
import { join } from 'node:path';

import { chromium } from 'playwright';

const base = (process.env.SCREENS_BASE || 'http://127.0.0.1:4173').replace(/\/$/, '');
const out = process.env.SCREENS_OUT || 'screens';
mkdirSync(out, { recursive: true });

const pages = [
  ['best-bets', '/'],
  ['best-bets-htft', '/?bet=group:HT%2FFT&min=1.70'],
  ['best-bets-card', '/?bet=group:HT%2FFT&min=1.70', true],
  ['value', '/value/'],
  ['explore', '/explore/'],
  ['rounds', '/rounds/'],
  ['report', '/report/'],
  ['tickets', '/tickets/'],
];

const viewports = [
  ['desktop', 1280, 800],
  ['mobile', 390, 844],
];

const browser = await chromium.launch();
try {
  for (const [label, width, height] of viewports) {
    const context = await browser.newContext({ viewport: { width, height } });
    const page = await context.newPage();
    for (const [name, path, open] of pages) {
      await page.goto(base + path, { waitUntil: 'networkidle' });
      await page.waitForTimeout(1500);
      if (open) {
        const button = page.locator('[aria-label="Details"]').first();
        await button.waitFor({ timeout: 15000 });
        await button.click();
        await page.waitForTimeout(600);
      }
      await page.screenshot({ path: join(out, `${label}-${name}.png`) });
      console.log(`screens: ${label}-${name}.png`);
    }
    await context.close();
  }
} finally {
  await browser.close();
}
