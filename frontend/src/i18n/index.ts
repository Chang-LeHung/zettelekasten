import { inject, ref, type App, type InjectionKey, type Plugin, type Ref } from 'vue'
import { en } from './en'
import { zh } from './zh'

export type Locale = 'en' | 'zh'

const STORAGE_KEY = 'zett.locale'

const messages: Record<Locale, Record<string, string>> = {
  en,
  zh,
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
