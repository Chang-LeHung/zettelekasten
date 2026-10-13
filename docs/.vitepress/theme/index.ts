import { h } from 'vue'
import DefaultTheme from 'vitepress/theme'

import HeroArt from './HeroArt.vue'
import './green.css'
import './home.css'

/**
 * VitePress's default theme is the documentation UI readers already know from
 * Vue's own docs; Zett swaps the palette (green instead of indigo), styles the
 * file name above a named code block, and gives the home page a hero picture.
 */
export default {
  extends: DefaultTheme,
  Layout: () =>
    h(DefaultTheme.Layout, null, {
      'home-hero-image': () => h(HeroArt),
    }),
}
