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

type Lang = 'en' | 'zh'

const COPY = {
  en: {
    prefix: '',
    guide: 'Guide',
    plugins: 'Plugins',
    userGuide: 'User guide',
    conversations: 'Conversations',
    chrome: 'Chrome extension',
    artifacts: 'Artifacts and the library',
    assets: 'Assets',
    tasks: 'Scheduled tasks',
    channels: 'Channels',
    settings: 'Settings and local data',
    cli: 'Command line',
    writing: 'Writing a plugin',
    agent: 'Agent plugins',
    channel: 'Channel plugins',
    weixin: 'WeChat channel plugin',
  },
  zh: {
    prefix: '/zh',
    guide: '指南',
    plugins: '插件',
    userGuide: '用户指南',
    conversations: '会话',
    chrome: 'Chrome 扩展',
    artifacts: '产物与产物库',
    assets: '资源',
    tasks: '定时任务',
    channels: '通信渠道',
    settings: '设置与本地数据',
    cli: '命令行',
    writing: '编写插件',
    agent: 'Agent 插件',
    channel: '渠道插件',
    weixin: '微信渠道插件',
  },
} as const

/** One locale's navigation, sidebar and interface strings; the page tree mirrors under `/zh/`. */
function themeFor(lang: Lang) {
  const t = COPY[lang]
  const p = t.prefix
  const zh = lang === 'zh'
  return {
    nav: [
      { text: t.guide, link: `${p}/guide/conversations`, activeMatch: `^${p}/guide/` },
      { text: t.plugins, link: `${p}/plugins/`, activeMatch: `^${p}/plugins/` },
      { text: 'agim SDK', link: `${p}/agim` },
      { text: 'GitHub', link: REPO_URL },
    ],
    sidebar: [
      {
        text: t.userGuide,
        items: [
          { text: t.conversations, link: `${p}/guide/conversations` },
          { text: t.chrome, link: `${p}/guide/chrome-extension` },
          { text: t.artifacts, link: `${p}/guide/artifacts` },
          { text: t.assets, link: `${p}/guide/assets` },
          { text: t.tasks, link: `${p}/guide/scheduled-tasks` },
          { text: t.channels, link: `${p}/guide/channels` },
          { text: t.settings, link: `${p}/guide/settings` },
          { text: t.cli, link: `${p}/guide/command-line` },
        ],
      },
      {
        text: t.plugins,
        items: [
          { text: t.writing, link: `${p}/plugins/` },
          { text: t.agent, link: `${p}/plugins/agent-plugins` },
          { text: t.channel, link: `${p}/plugins/channel-plugins` },
          { text: 'agim SDK', link: `${p}/agim` },
          { text: t.weixin, link: `${p}/weixin` },
        ],
      },
    ],
    editLink: {
      pattern: `${REPO_URL}/edit/main/docs/:path`,
      text: zh ? '在 GitHub 上编辑此页' : 'Edit this page on GitHub',
    },
    outline: { level: [2, 3] as [number, number], label: zh ? '本页目录' : 'On this page' },
    docFooter: zh ? { prev: '上一页', next: '下一页' } : { prev: 'Previous page', next: 'Next page' },
    lastUpdated: {
      text: zh ? '最后更新于' : 'Last updated',
      formatOptions: { dateStyle: 'medium', timeStyle: 'short' } as const,
    },
    footer: {
      message: zh
        ? 'Zett 运行在你的电脑上，把你的知识保存在属于你的文件夹里。'
        : 'Zett runs on your computer and keeps your knowledge in a folder you own.',
      copyright: zh ? '基于 MIT 许可发布' : 'Released under the MIT license',
    },
    ...(zh
      ? {
          returnToTopLabel: '回到顶部',
          sidebarMenuLabel: '菜单',
          darkModeSwitchLabel: '主题',
          lightModeSwitchTitle: '切换到浅色模式',
          darkModeSwitchTitle: '切换到深色模式',
          langMenuLabel: '切换语言',
          skipToContentLabel: '跳到正文',
        }
      : {}),
  }
}

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
  locales: {
    root: { label: 'English', lang: 'en', themeConfig: themeFor('en') },
    zh: {
      label: '简体中文',
      lang: 'zh-CN',
      link: '/zh/',
      description: '在你自己的电脑上，与 AI 一起思考的工作区。',
      themeConfig: themeFor('zh'),
    },
  },
  themeConfig: {
    search: {
      provider: 'local',
      options: {
        locales: {
          zh: {
            translations: {
              button: { buttonText: '搜索文档', buttonAriaLabel: '搜索文档' },
              modal: {
                displayDetails: '显示详细列表',
                resetButtonTitle: '清除查询条件',
                backButtonTitle: '关闭搜索',
                noResultsText: '没有找到相关结果',
                footer: {
                  selectText: '选择',
                  selectKeyAriaLabel: '回车',
                  navigateText: '切换',
                  navigateUpKeyAriaLabel: '上方向键',
                  navigateDownKeyAriaLabel: '下方向键',
                  closeText: '关闭',
                  closeKeyAriaLabel: 'esc',
                },
              },
            },
          },
        },
      },
    },
    socialLinks: [{ icon: 'github', link: REPO_URL }],
  },
})
