#!/usr/bin/env node
/**
 * Render the social card at web/assets/og.png from og-card.html.
 *
 *   node web/tools/render-og.mjs
 *
 * Needs Playwright with Chrome or Chromium available. The card is 1200×630, the
 * size Open Graph and Twitter expect; re-run it whenever the card copy changes.
 */

import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import process from 'node:process';

const here = dirname(fileURLToPath(import.meta.url));
const template = resolve(here, 'og-card.html');
const output = resolve(here, '..', 'assets', 'og.png');

const { chromium } = await import('playwright');

async function launch() {
  for (const options of [{ channel: 'chrome' }, {}]) {
    try {
      return await chromium.launch(options);
    } catch {
      // try the next option; the bundled browser may be the only one present
    }
  }
  throw new Error('No Chrome or Chromium available for Playwright');
}

const browser = await launch();
const page = await browser.newPage({ viewport: { width: 1200, height: 630 }, deviceScaleFactor: 1 });
await page.goto(`file://${template}`, { waitUntil: 'networkidle' });
await page.evaluate(() => document.fonts?.ready);
await page.waitForTimeout(300);
await page.screenshot({ path: output });
await browser.close();

console.log(`wrote ${output}`);
process.exit(0);
