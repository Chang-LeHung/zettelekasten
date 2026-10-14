import { createApp } from 'vue'
import App from './App.vue'
import { i18nPlugin } from './i18n'
import './styles/previewSurface.css'
import './styles/cardStatus.css'
import './styles/artifactLifecycle.css'
import './styles/polish.css'
import './styles/notion.css'

createApp(App).use(i18nPlugin).mount('#app')
