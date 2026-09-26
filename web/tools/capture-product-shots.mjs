#!/usr/bin/env node
/**
 * Capture the landing page's product screenshots from a throwaway Zett instance.
 *
 * Start a demo server whose data lives in a temporary directory (never the real
 * `~/.zettelekasten`) first:
 *
 *   DEMO=$(mktemp -d)
 *   ZETT_STORAGE_ROOT=$DEMO ZETT_DATABASE_PATH=$DEMO/zett.db \
 *   ZETT_AGENT_DATABASE_PATH=$DEMO/agent.db ZETT_PROCESS_SUPERVISOR_ENABLED=false \
 *   uv run --directory backend uvicorn zett.main:app --host 127.0.0.1 --port 6520
 *
 * Then:
 *
 *   node web/tools/capture-product-shots.mjs            # seeds and captures
 *   node web/tools/capture-product-shots.mjs --base http://127.0.0.1:6520
 *
 * It seeds one provider, one scheduled task, one static asset, a few artifacts
 * with tags, and then screenshots the views the landing page shows. All content
 * is synthetic and the instance is disposable.
 */

import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
import process from 'node:process';

const args = process.argv.slice(2);
const flag = (name, fallback) => {
  const index = args.indexOf(name);
  return index === -1 ? fallback : args[index + 1];
};

const base = flag('--base', 'http://127.0.0.1:6520');
const outdir = resolve(flag('--out', 'web/assets/product'));
const scale = Number(flag('--scale', 2));

async function api(path, { method = 'GET', body, headers = {} } = {}) {
  const response = await fetch(`${base}${path}`, {
    method,
    headers: { 'content-type': 'application/json', ...headers },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`${method} ${path} -> ${response.status} ${await response.text()}`);
  }
  return response.status === 204 ? null : response.json();
}

/* ------------------------------------------------------------------ seed */

async function seed() {
  const { conversation_id: sessionId } = await api('/api/agent/start', { method: 'POST' });

  const provider = await api('/api/ai/providers', {
    method: 'POST',
    body: { name: 'OpenAI · gpt-5', provider: 'openai', model: 'gpt-5', api_key: 'sk-demo-not-a-real-key' },
  });

  await api('/api/library/tags', { method: 'POST', body: { name: 'Technology' } });
  await api('/api/library/tags', { method: 'POST', body: { name: 'Python', parent_path: 'Technology' } });
  await api('/api/library/tags', { method: 'POST', body: { name: 'Ideas' } });

  const artifacts = [
    {
      content: {
        artifact_type: 'card',
        card_type: 'idea',
        title: 'Local-first beats sync for personal notes',
        summary: 'A file on disk survives the company that made the app.',
        content:
          'A file on disk survives the company that made the app. Sync is a feature you can add later; ownership is not.\n\nKeeping the canonical copy on your own disk makes export, backup, and migration somebody else\'s feature request instead of your problem.',
        suggested_tags: [
          { path: 'Technology', name: 'Technology' },
          { path: 'Technology/Python', name: 'Python' },
        ],
      },
    },
    {
      content: {
        artifact_type: 'article',
        subtitle: 'What a compaction checkpoint keeps, and what it drops',
        title: 'How Zett keeps a long conversation cheap',
        summary: 'Compaction replaces old turns with a checkpoint while the raw log stays intact.',
        content:
          '## The problem\n\nEvery turn re-reads the conversation, so cost grows with its length — until the model refuses the request outright.\n\n## What compaction keeps\n\nOlder turns collapse into a checkpoint. A recent verbatim tail survives, so the assistant still remembers what you just said.\n\n## What it never touches\n\nThe raw log. Immutable messages and every earlier snapshot stay on disk, so a compacted conversation can still be audited and rebuilt.',
        suggested_tags: [{ path: 'Technology', name: 'Technology' }],
      },
    },
    {
      content: {
        artifact_type: 'slides',
        subtitle: 'A team lunch talk',
        title: 'Ten minutes on local-first notes',
        summary: 'Eight slides on why the file on disk matters.',
        content:
          '# Ten minutes on local-first notes\n\n## Why the file on disk matters\n\nStaff talk · 2026\n\n---\n# Where the notes live\n\n--\n## A directory, not a service\n\n- One folder you can open in Finder\n- Works offline, on a plane, in ten years\n\n--\n## The trade you are making\n\n- You own backup and migration\n- You keep every byte of your thinking',
        suggested_tags: [{ path: 'Ideas', name: 'Ideas' }],
      },
    },
  ];

  const created = [];
  for (const artifact of artifacts) {
    created.push(
      await api(`/api/agent/${sessionId}/artifacts`, {
        method: 'POST',
        body: { ...artifact, status: 'saved' },
      }),
    );
  }

  // A second conversation with a card still in draft, so the library shows both states.
  const { conversation_id: draftSession } = await api('/api/agent/start', { method: 'POST' });
  await api(`/api/agent/${draftSession}/artifacts`, {
    method: 'POST',
    body: {
      status: 'draft',
      content: {
        artifact_type: 'card',
        card_type: 'todo',
        title: 'Try the PDF pipeline end to end',
        summary: 'Compile a paper, commit it, then publish the artifact.',
        content: '- `git init` the project directory\n- add a `.gitignore` for the LaTeX build files\n- commit with a Conventional Commit message\n- publish the artifact once the tree is clean',
      },
    },
  });

  const asset = new FormData();
  asset.append('file', new Blob(['# Reading list\n\n- Parnas, On the Criteria To Be Used in Decomposing Systems into Modules\n'], { type: 'text/markdown' }), 'reading-list.md');
  await fetch(`${base}/api/assets/upload?name=reading-list.md`, { method: 'POST', body: asset }).then((r) => r.json());

  await api('/api/scheduled-tasks', {
    method: 'POST',
    body: {
      name: 'Weekly reading digest',
      schedule: { expression: '0 9 * * 1', timezone: 'Asia/Shanghai' },
      action: {
        kind: 'agent_prompt',
        payload: { provider_id: provider.id, message: 'Summarize what I saved this week into one card.', reasoning_effort: 'medium' },
      },
      enabled: true,
    },
  });

  return { sessionId, draftSession, artifactId: created[1].id, providerId: provider.id };
}

/* ------------------------------------------------------------- capture */

const VIEWS = [
  { name: 'library', nav: 'Artifacts' },
  { name: 'static-assets', nav: 'Static Assets' },
  { name: 'scheduled-tasks', nav: 'Scheduled tasks' },
  { name: 'channels', nav: 'Channels' },
];

async function capture({ sessionId, artifactId }) {
  const { chromium } = await import('playwright');
  const browser = await chromium.launch({ channel: 'chrome' });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 940 },
    deviceScaleFactor: scale,
    colorScheme: 'light',
  });
  const page = await context.newPage();
  await page.goto(base, { waitUntil: 'networkidle' });
  await mkdir(outdir, { recursive: true });

  const shot = async (name, clip) => {
    await page.waitForTimeout(700);
    await page.screenshot({ path: resolve(outdir, `${name}.png`), clip });
  };

  // The conversation workspace: sidebar, chat, artifact column.
  await page.evaluate((id) => {
    window.localStorage.setItem('zett.active-session-id', id);
  }, sessionId);
  await page.reload({ waitUntil: 'networkidle' });
  await shot('workspace', { x: 0, y: 0, width: 1440, height: 940 });

  for (const view of VIEWS) {
    await page.getByRole('button', { name: view.nav, exact: true }).first().click();
    await page.waitForTimeout(900);
    await shot(view.name, { x: 0, y: 0, width: 1440, height: 940 });
  }

  // Library reader: the published article with its tags.
  await page.getByRole('button', { name: 'Artifacts', exact: true }).first().click();
  await page.waitForTimeout(800);
  await page.getByRole('button', { name: /How Zett keeps a long conversation cheap/ }).first().click();
  await shot('reader', { x: 240, y: 60, width: 960, height: 860 });

  // Settings, for the provider list.
  await page.getByRole('button', { name: 'Settings', exact: true }).first().click();
  await page.waitForTimeout(900);
  await shot('settings', { x: 0, y: 0, width: 1440, height: 940 });

  await browser.close();
  console.log(`artifact for reference: ${artifactId}`);
}

const seeded = await seed();
console.log('seeded demo data:', seeded);
await capture(seeded);
console.log(`wrote screenshots to ${outdir}`);
