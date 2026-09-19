import { inject, ref, type App, type InjectionKey, type Plugin, type Ref } from 'vue'

export type Locale = 'en' | 'zh'

const STORAGE_KEY = 'zett.locale'

const messages: Record<Locale, Record<string, string>> = {
  en: {
    'brand.subtitle': 'Knowledge cards',
    'nav.workspace': 'AI workspace',
    'nav.library': 'Library',
    'nav.conversations': 'Conversations',
    'nav.settings': 'Settings',
    'nav.newConversation': 'Start a new session',
    'nav.loadMore': 'Load more',
    'nav.loading': 'Loading…',
    'nav.noConversations': 'No previous conversations.',
    'nav.collections': 'Collections',
    'nav.tagsEmpty': 'Tags will appear here.',
    'nav.manageTags': 'Manage tags',
    'nav.expand': 'Expand',
    'nav.collapse': 'Collapse',
    'nav.deleteTag': 'Delete {path}',
    'search.placeholder': 'Search cards, articles, slides, and sources',
    'search.clear': 'Clear search',
    'search.newCard': 'New card',
    'settings.language': 'Language',
    'settings.english': 'English',
    'settings.chinese': '中文',
    'settings.usage': 'Usage',
    'settings.providersLimits': 'Providers & limits',
    'composer.model': 'Model',
    'composer.thinking': 'Thinking',
    'composer.off': 'Off',
    'composer.low': 'Low',
    'composer.medium': 'Medium',
    'composer.high': 'High',
    'composer.shell': 'Shell',
    'composer.review': 'Review',
    'composer.allowAll': 'Allow all',
    'composer.reviewDescription': 'Approve shell commands',
    'composer.allowAllDescription': 'Run shell commands directly',
    'composer.nextMessage': 'For the next message',
    'composer.totalIn': 'Total in',
    'composer.totalOut': 'Total out',
    'composer.cache': 'Cache',
    'composer.speed': 'Speed',
    'composer.enterToSend': 'Enter to send',
    'composer.enterToQueue': 'Enter to queue',
    'composer.messagePlaceholder': 'Message Zett Agent…',
    'composer.continuePlaceholder': 'Continue the conversation…',
    'shellApproval.title': 'Shell command approval',
    'shellApproval.description': 'The command will run in the current workspace · timeout {seconds}s.',
    'shellApproval.waiting': 'Waiting for you',
    'shellApproval.remember': 'Always allow this exact command',
    'shellApproval.once': 'This decision applies to this command only.',
    'shellApproval.abort': 'Abort',
    'shellApproval.execute': 'Execute',
    'shellApproval.sending': 'Sending…',
  },
  zh: {
    'brand.subtitle': '知识卡片',
    'nav.workspace': 'AI 工作台',
    'nav.library': '知识库',
    'nav.conversations': '会话',
    'nav.settings': '设置',
    'nav.newConversation': '新建会话',
    'nav.loadMore': '加载更多',
    'nav.loading': '加载中…',
    'nav.noConversations': '暂无历史会话。',
    'nav.collections': '分类',
    'nav.tagsEmpty': '标签会显示在这里。',
    'nav.manageTags': '管理标签',
    'nav.expand': '展开',
    'nav.collapse': '收起',
    'nav.deleteTag': '删除 {path}',
    'search.placeholder': '搜索卡片、文章、幻灯片和来源',
    'search.clear': '清除搜索',
    'search.newCard': '新建卡片',
    'settings.language': '语言',
    'settings.english': 'English',
    'settings.chinese': '中文',
    'settings.usage': '使用情况',
    'settings.providersLimits': 'Provider 与限制',
    'composer.model': '模型',
    'composer.thinking': '思考',
    'composer.off': '关闭',
    'composer.low': '低',
    'composer.medium': '中',
    'composer.high': '高',
    'composer.shell': 'Shell',
    'composer.review': '审核',
    'composer.allowAll': '全部放行',
    'composer.reviewDescription': '执行前需要确认',
    'composer.allowAllDescription': '直接执行 Shell 命令',
    'composer.nextMessage': '应用于下一条消息',
    'composer.totalIn': '输入',
    'composer.totalOut': '输出',
    'composer.cache': '缓存',
    'composer.speed': '速度',
    'composer.enterToSend': '回车发送',
    'composer.enterToQueue': '回车加入队列',
    'composer.messagePlaceholder': '给 Zett Agent 发送消息…',
    'composer.continuePlaceholder': '继续对话…',
    'shellApproval.title': 'Shell 命令审核',
    'shellApproval.description': '命令将在当前工作区执行 · 超时 {seconds} 秒。',
    'shellApproval.waiting': '等待你的决定',
    'shellApproval.remember': '始终允许这条完全相同的命令',
    'shellApproval.once': '此决定仅对当前命令有效。',
    'shellApproval.abort': '中止',
    'shellApproval.execute': '执行',
    'shellApproval.sending': '发送中…',
    'Settings': '设置',
    'Preferences': '偏好设置',
    'AI providers': 'AI Provider',
    'Keep multiple model connections and choose one for each conversation.': '保存多个模型连接，并为每个会话选择使用的模型。',
    'New provider': '新建 Provider',
    'Connection name': '连接名称',
    'Provider': 'Provider',
    'Model': '模型',
    'Base URL': 'Base URL',
    'API key': 'API Key',
    'Temperature': '温度',
    'API mode': 'API 模式',
    'Conversation limits': '会话限制',
    'Control local limits applied to new Agent requests.': '控制新 Agent 请求使用的本地限制。',
    'Images per message': '每条消息图片数',
    'Model steps per turn': '每轮模型步数',
    'Max asset file size': '最大文件大小',
    'Maximum size for an uploaded image or file in this conversation.': '当前会话中上传图片或文件的最大大小。',
    'Compact context at': '压缩上下文阈值',
    'Keep recent context': '保留最近上下文',
    'Save limits': '保存限制',
    'Model activity': '模型活动',
    'Daily token requests recorded from completed LLM calls.': '来自已完成 LLM 调用的每日 Token 请求。',
    'Last 12 months': '最近 12 个月',
    'By model': '按模型',
    'Request volume and token usage for every provider model.': '查看每个 Provider 模型的请求量和 Token 使用量。',
    'Your knowledge': '你的知识',
    'All knowledge': '全部知识',
    'Search library': '搜索知识库',
    'Results for “{query}”': '“{query}”的搜索结果',
    '{count} items in your library': '知识库中有 {count} 项内容',
    '{count} matching items': '找到 {count} 项匹配内容',
    'Type': '类型',
    'All': '全部',
    'Cards': '卡片',
    'Articles': '文章',
    'Slides': '幻灯片',
    'PDFs': 'PDF',
    'Your library is ready': '知识库已就绪',
    'Capture a thought and let AI shape it into a useful card, article, or slide deck.': '记录一个想法，让 AI 整理成有用的卡片、文章或幻灯片。',
    'Capture an idea': '记录想法',
    'Summarize a note': '总结笔记',
    'Nothing found': '没有找到内容',
    'Try a different phrase or browse your collections.': '尝试其他关键词，或浏览你的分类。',
    'Browse library': '浏览知识库',
    'Create your first card': '创建第一张卡片',
    'Presentation · {count} slides': '演示文稿 · {count} 页',
    'Assets': '资源',
    'Session resources': '会话资源',
    'Add text note': '添加文本笔记',
    'Add link': '添加链接',
    'Upload files': '上传文件',
    'Search assets': '搜索资源',
    'Drop or paste assets here': '拖入或粘贴资源',
    'No assets yet': '暂无资源',
    'No matching assets': '没有匹配的资源',
    'What should we remember?': '想记住什么？',
    'Share a rough thought, excerpt, or question. You can refine the result through conversation before saving it.': '分享一个初步想法、摘录或问题。保存前可以通过对话继续完善。',
    'Zettelkasten Agent': 'Zettelkasten Agent',
    'Turn a conversation into knowledge': '把对话转化为知识',
    'Zettelkasten Agent online': 'Zettelkasten Agent 在线',
    'Workspace': '工作台',
    'Trace': '轨迹',
    'Close': '关闭',
    'Artifacts': '产物',
    'Asset type': '资源类型',
    'Documents': '文档',
    'Images': '图片',
    'Links': '链接',
    'Notes': '笔记',
    'Code': '代码',
    '{count} assets': '{count} 个资源',
    '{count} asset': '{count} 个资源',
    'Newest': '最新',
    'Add a link': '添加链接',
    'Add a note': '添加笔记',
    'Link name': '链接名称',
    'Note name': '笔记名称',
    'Text content': '文本内容',
    'Add asset': '添加资源',
    'Cancel': '取消',
    'Try another search or filter.': '尝试其他搜索或筛选条件。',
    'Add reference material for this conversation.': '为此会话添加参考资料。',
    'Click this area, then press Ctrl/⌘ + V': '点击此区域，然后按 Ctrl/⌘ + V',
    '{count} in this conversation': '此会话中有 {count} 项',
    'Updating': '更新中',
    'No artifacts yet': '暂无产物',
    'Keep talking with Zett Agent. Cards, articles, slides, and images will appear here when the conversation produces them.': '继续与 Zett Agent 对话。当会话生成卡片、文章、幻灯片或图片时，会显示在这里。',
    'Edit': '编辑',
    'Preview': '预览',
    'Card type': '卡片类型',
    'Project directory': '项目目录',
    'PDF filename': 'PDF 文件名',
    'Source files stay in the project directory. Compile the PDF before saving this reference.': '源文件保存在项目目录中。保存此引用前请先编译 PDF。',
    'Artifact display mode': '产物显示模式',
    'note': '笔记',
    'idea': '想法',
    'quote': '引用',
    'todo': '待办',
    'reference': '参考',
    'card': '卡片',
    'article': '文章',
    'slides': '幻灯片',
    'latex_pdf': 'PDF',
    '{count} requests · {days} active days': '{count} 次请求 · {days} 个活跃日',
    '{count} requests · {days} active day': '{count} 次请求 · {days} 个活跃日',
    '{count} tokens': '{count} Token',
    'Less': '少',
    'More': '多',
    'requests': '请求次数',
    'request': '请求次数',
    'Input': '输入',
    'Output': '输出',
    'Total': '总计',
    'Cache read': '缓存读取',
    'Cache hit rate': '缓存命中率',
    'Cache write': '缓存写入',
    'Reasoning': '推理',
    'Daily model token activity': '每日模型 Token 活动',
    'API requests': 'API 请求',
    'Tokens': 'Token',
    'Unknown provider': '未知 Provider',
    'Unknown model': '未知模型',
  },
}

export type MessageKey = string

export interface I18n {
  locale: Ref<Locale>
  t: (key: MessageKey, params?: Record<string, string | number>) => string
  setLocale: (locale: Locale) => void
}

const I18N_KEY: InjectionKey<I18n> = Symbol('zett-i18n')

export function createI18n(initial: Locale = 'en'): I18n {
  const locale = ref<Locale>(initial)
  const t = (key: MessageKey, params: Record<string, string | number> = {}): string => {
    const template = messages[locale.value][key] ?? messages.en[key] ?? key
    return template.replace(/\{(\w+)\}/g, (_match, name: string) => String(params[name] ?? `{${name}}`))
  }
  const setLocale = (next: Locale): void => {
    locale.value = next
    if (typeof window !== 'undefined' && typeof window.localStorage?.setItem === 'function') {
      window.localStorage.setItem(STORAGE_KEY, next)
    }
    if (typeof document !== 'undefined') document.documentElement.lang = next === 'zh' ? 'zh-CN' : 'en'
  }
  return { locale, t, setLocale }
}

function initialLocale(): Locale {
  if (typeof window === 'undefined') return 'en'
  try {
    return typeof window.localStorage?.getItem === 'function' && window.localStorage.getItem(STORAGE_KEY) === 'zh'
      ? 'zh'
      : 'en'
  } catch {
    return 'en'
  }
}

export const i18n = createI18n(initialLocale())

export function useI18n(): I18n {
  return inject(I18N_KEY, i18n)
}

export const i18nPlugin: Plugin = {
  install(app: App) {
    app.provide(I18N_KEY, i18n)
    app.config.globalProperties.$t = i18n.t
    app.config.globalProperties.$locale = i18n.locale
    if (typeof document !== 'undefined') document.documentElement.lang = i18n.locale.value === 'zh' ? 'zh-CN' : 'en'
  },
}

declare module '@vue/runtime-core' {
  interface ComponentCustomProperties {
    $t: I18n['t']
    $locale: Ref<Locale>
  }
}
