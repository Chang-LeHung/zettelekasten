<script setup lang="ts">
import type { ArtifactDiff } from '../utils/artifactDiff'
import { useI18n } from '../i18n'

defineProps<{ diff: ArtifactDiff }>()

const { t } = useI18n()

const FIELD_KEYS: Record<string, string> = {
  Title: 'artifactDiff.title',
  Summary: 'artifactDiff.summary',
  Subtitle: 'artifactDiff.subtitle',
  'Card type': 'artifactDiff.cardType',
  Body: 'artifactDiff.body',
}

function fieldLabel(label: string): string {
  return t(FIELD_KEYS[label] ?? label)
}

function marker(kind: 'context' | 'added' | 'removed'): string {
  if (kind === 'added') return '+'
  if (kind === 'removed') return '−'
  return ' '
}
</script>

<template>
  <div class="artifact-diff">
    <p v-if="!diff.changed" class="artifact-diff-empty">{{ $t('artifactDiff.empty') }}</p>
    <section v-for="field in diff.fields" :key="field.label" class="artifact-diff-field" :class="{ changed: field.changed }">
      <header>
        <strong>{{ fieldLabel(field.label) }}</strong>
        <small>{{ field.changed ? $t('artifactDiff.changed') : $t('artifactDiff.unchanged') }}</small>
      </header>
      <template v-if="field.changed">
        <template v-for="(hunk, hunkIndex) in field.hunks" :key="`${field.label}-${hunkIndex}`">
          <p v-if="hunkIndex > 0" class="artifact-diff-gap" aria-hidden="true">⋯</p>
          <pre class="artifact-diff-body"><span
            v-for="(line, lineIndex) in hunk"
            :key="`${field.label}-${hunkIndex}-${lineIndex}`"
            :class="`diff-${line.kind}`"
          >{{ marker(line.kind) }}{{ line.text }}
</span></pre>
        </template>
      </template>
    </section>
    <p class="artifact-diff-note">{{ $t('artifactDiff.note') }}</p>
  </div>
</template>

<style scoped>
.artifact-diff { display: flex; flex-direction: column; gap: .55rem; }
.artifact-diff-empty, .artifact-diff-note { margin: 0; color: #7d8781; font-size: .68rem; }
.artifact-diff-field { border: 1px solid #e6ebe8; border-radius: .6rem; background: #fff; overflow: hidden; }
.artifact-diff-field > header { display: flex; align-items: baseline; justify-content: space-between; gap: .6rem; padding: .38rem .6rem; border-bottom: 1px solid #edf0ee; background: #f7faf8; }
.artifact-diff-field > header strong { color: #4b554f; font-size: .68rem; font-weight: 700; }
.artifact-diff-field > header small { color: #8b948e; font-size: .6rem; text-transform: uppercase; letter-spacing: .04em; }
.artifact-diff-field.changed > header small { color: #b07d24; }
.artifact-diff-body { margin: 0; padding: .35rem .5rem; overflow-x: auto; font-family: "SFMono-Regular", Consolas, monospace; font-size: .66rem; line-height: 1.45; white-space: pre-wrap; word-break: break-word; }
.artifact-diff-body span { display: block; padding: 0 .25rem; border-radius: .2rem; }
.artifact-diff-body .diff-context { color: #6b746e; }
.artifact-diff-body .diff-added { color: #21613f; background: #e8f5ec; }
.artifact-diff-body .diff-removed { color: #8c2f2f; background: #fbeceb; }
.artifact-diff-gap { margin: 0; padding: 0 .55rem; color: #a4ada7; font-size: .6rem; text-align: center; }
</style>
