<script setup>
import { onMounted, ref } from 'vue'

const API = 'http://127.0.0.1:8000/api'
const call = (path, options = {}) => fetch(API + path, { headers: { 'Content-Type': 'application/json' }, ...options }).then((r) => r.json())

const cards = ref([])
const tags = ref([])
const query = ref('')
const selectedTag = ref(null)
const mode = ref('list')
const raw = ref('')
const analysis = ref(null)
const loading = ref(false)
const notice = ref('')
const selectedSuggestions = ref([])
const ai = ref({ provider: 'openai-compatible', model: '', base_url: '', api_key: '', temperature: 0.2, enabled: true })
const tagName = ref('')
const tagParent = ref(null)

const flatten = (nodes, depth = 0) => nodes.flatMap((tag) => [{ ...tag, depth }, ...flatten(tag.children || [], depth + 1)])

async function load() {
  tags.value = await call('/tags')
  const params = new URLSearchParams()
  if (query.value) params.set('q', query.value)
  if (selectedTag.value) params.set('tag_id', selectedTag.value)
  cards.value = await call(`/cards?${params}`)
}

async function loadAI() {
  const data = await call('/settings/ai')
  if (data) ai.value = { ...ai.value, ...data, api_key: '' }
}

async function analyze() {
  loading.value = true
  analysis.value = await call('/cards/analyze', { method: 'POST', body: JSON.stringify({ raw_content: raw.value }) })
  selectedSuggestions.value = analysis.value.suggested_tags.map((tag) => tag.path)
  loading.value = false
}

async function save() {
  const card = analysis.value
  const tagIds = flatten(tags.value).filter((tag) => selectedSuggestions.value.includes(tag.path)).map((tag) => tag.id)
  await call('/cards', { method: 'POST', body: JSON.stringify({ type: card.type, title: card.title, content: card.content, summary: card.summary, raw_content: raw.value, tag_ids: tagIds }) })
  raw.value = ''
  analysis.value = null
  selectedSuggestions.value = []
  mode.value = 'list'
  await load()
}

async function saveAI() {
  await call('/settings/ai', { method: 'PUT', body: JSON.stringify(ai.value) })
  notice.value = 'AI settings saved'
}

async function addTag() {
  if (!tagName.value) return
  await call('/tags', { method: 'POST', body: JSON.stringify({ name: tagName.value, parent_id: tagParent.value || null }) })
  tagName.value = ''
  await load()
  notice.value = 'Tag created'
}

onMounted(() => { load(); loadAI() })
</script>

<template>
  <div class="app">
    <header><h1>Knowledge Cards</h1><button @click="mode = 'new'">+ New Card</button><button class="ghost" @click="mode = 'settings'">Settings</button></header>
    <main>
      <aside><input v-model="query" placeholder="Search cards..." @keyup.enter="load"><button class="all" @click="selectedTag = null; load()">All Cards</button><h3>Domains and Tags</h3><div v-for="tag in flatten(tags)" :key="tag.id" class="tag" :style="{ paddingLeft: `${12 + tag.depth * 18}px` }" @click="selectedTag = tag.id; load()">{{ tag.depth ? '↳ ' : '' }}{{ tag.name }} <small>{{ tag.card_count }}</small></div></aside>
      <section v-if="mode === 'list'"><div class="section-title"><h2>{{ selectedTag ? 'Filtered Cards' : 'Recent Cards' }}</h2><span>{{ cards.length }} cards</span></div><article v-for="card in cards" :key="card.id" class="card"><div><span class="pill">{{ card.type }}</span><h3>{{ card.title }}</h3><p>{{ card.summary || card.content }}</p><div><span v-for="tag in card.tags" :key="tag.id" class="chip">{{ tag.path }}</span></div></div><time>{{ new Date(card.updated_at).toLocaleString() }}</time></article><div v-if="!cards.length" class="empty">No cards yet. Capture an idea.</div></section>
      <section v-else-if="mode === 'new'" class="editor"><h2>Organize a New Card</h2><textarea v-model="raw" placeholder="Paste a rough idea, note, or knowledge snippet..."></textarea><button :disabled="loading || !raw" @click="analyze">{{ loading ? 'Analyzing...' : 'Organize with AI' }}</button><div v-if="analysis" class="preview"><label>Type <input v-model="analysis.type"></label><label>Title <input v-model="analysis.title"></label><label>Summary <input v-model="analysis.summary"></label><label>Content <textarea v-model="analysis.content"></textarea></label><h3>Suggested Tags</h3><div v-for="tag in analysis.suggested_tags" :key="tag.path" class="suggestion"><input v-model="selectedSuggestions" type="checkbox" :value="tag.path"> {{ tag.path }} <small>{{ Math.round(tag.confidence * 100) }}%</small></div><button @click="save">Save Card</button></div></section>
      <section v-else class="editor"><h2>AI Settings</h2><p>API keys are never returned in full by the backend.</p><label>Provider<select v-model="ai.provider"><option>openai-compatible</option><option>openai</option><option>anthropic</option><option>gemini</option><option>ollama</option></select></label><label>Model<input v-model="ai.model" placeholder="deepseek-chat or llama3.2"></label><label>Base URL<input v-model="ai.base_url" placeholder="Optional compatible API or Ollama URL"></label><label>API Key<input v-model="ai.api_key" type="password" placeholder="Leave empty to keep the current key"></label><label>Temperature<input v-model.number="ai.temperature" type="number" min="0" max="2" step=".1"></label><label><input v-model="ai.enabled" type="checkbox"> Enable AI</label><br><button @click="saveAI">Save AI Settings</button><p>{{ notice }}</p><h2>Add Tag</h2><label>Name<input v-model="tagName" placeholder="e.g. Decorators"></label><label>Parent<select v-model="tagParent"><option :value="null">Root tag</option><option v-for="tag in flatten(tags)" :key="tag.id" :value="tag.id">{{ '  '.repeat(tag.depth) }}{{ tag.path }}</option></select></label><button @click="addTag">Create Tag</button></section>
    </main>
  </div>
</template>
