import { describe, expect, it } from 'vitest'
import { createI18n } from './index'

describe('i18n', () => {
  it('defaults to English and switches to Chinese', () => {
    const instance = createI18n('en')

    expect(instance.t('nav.artifacts')).toBe('Artifacts')
    expect(instance.t('shellApproval.title')).toBe('Shell command approval')

    instance.setLocale('zh')

    expect(instance.t('nav.artifacts')).toBe('产物')
    expect(instance.t('shellApproval.title')).toBe('Shell 命令审核')
  })

  it('interpolates message parameters', () => {
    const instance = createI18n('en')

    expect(instance.t('shellApproval.description', { seconds: 30 })).toContain('timeout 30s')
    instance.setLocale('zh')
    expect(instance.t('shellApproval.description', { seconds: 30 })).toContain('超时 30 秒')
  })
})
