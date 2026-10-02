import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vitepress'

import { fenceTitlePlugin, snippetPlugin } from './markdown'

const here = path.dirname(fileURLToPath(import.meta.url))
const repo = path.resolve(here, '../..')

/**
 * `make site` serves the composed tree at the repository root, so the
 * documentation lives under `/docs/`. The Docs workflow publishes the project
 * site instead, where the same tree sits under `/zettelekasten/docs/`.
 */
const base = process.env.DOCS_BASE ?? '/docs/'

const REPO_URL = 'https://github.com/Chang-LeHung/zettelekasten'

export default defineConfig({
  outDir: path.resolve(repo, 'site/docs'),
  // Internal engineering notes live beside the guides and stay unpublished.
  srcExclude: ['internal/**'],
  base,
  cleanUrls: true,
  title: 'Zett',
  description: 'A workspace for thinking with an AI, on your own computer.',
  head: [
    ['link', { rel: 'icon', href: 'favicon.ico' }],
    ['meta', { property: 'og:type', content: 'website' }],
    ['meta', { property: 'og:site_name', content: 'Zett' }],
  ],
  markdown: {
    config: (md) => {
      snippetPlugin(md, repo)
      fenceTitlePlugin(md)
    },
  },
  themeConfig: {
    nav: [
      { text: 'Guide', link: '/guide/conversations', activeMatch: '^/guide/' },
      { text: 'Plugins', link: '/plugins/', activeMatch: '^/plugins/' },
      { text: 'agim SDK', link: '/agim' },
      { text: 'GitHub', link: REPO_URL },
    ],
    sidebar: [
      {
        text: 'User guide',
        items: [
          { text: 'Conversations', link: '/guide/conversations' },
          { text: 'Chrome extension', link: '/guide/chrome-extension' },
          { text: 'Artifacts and the library', link: '/guide/artifacts' },
          { text: 'Assets', link: '/guide/assets' },
          { text: 'Scheduled tasks', link: '/guide/scheduled-tasks' },
          { text: 'Channels', link: '/guide/channels' },
          { text: 'Settings and local data', link: '/guide/settings' },
          { text: 'Command line', link: '/guide/command-line' },
        ],
      },
      {
        text: 'Plugins',
        items: [
          { text: 'Writing a plugin', link: '/plugins/' },
          { text: 'Agent plugins', link: '/plugins/agent-plugins' },
          { text: 'Channel plugins', link: '/plugins/channel-plugins' },
          { text: 'agim SDK', link: '/agim' },
          { text: 'WeChat channel plugin', link: '/weixin' },
        ],
      },
    ],
    search: { provider: 'local' },
    socialLinks: [{ icon: 'github', link: REPO_URL }],
    editLink: { pattern: `${REPO_URL}/edit/main/docs/:path`, text: 'Edit this page on GitHub' },
    outline: { level: [2, 3], label: 'On this page' },
    docFooter: { prev: 'Previous page', next: 'Next page' },
    lastUpdated: {
      text: 'Last updated',
      formatOptions: { dateStyle: 'medium', timeStyle: 'short' },
    },
    footer: {
      message: 'Zett runs on your computer and keeps your knowledge in a folder you own.',
      copyright: 'Released under the MIT license',
    },
  },
})
