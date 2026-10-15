<script setup lang="ts">
import { defineAsyncComponent } from 'vue'
import { closeSlidesFullscreen } from '../app/library/actions'
import { fullscreenSlidesItem } from '../app/library/state'

const SlidesPreview = defineAsyncComponent(() => import('../components/SlidesPreview.vue'))
</script>

<template>
  <Teleport to="body">
    <section v-if="fullscreenSlidesItem" ref="librarySlidesStage" class="library-slides-fullscreen" role="dialog" aria-modal="true" :aria-label="fullscreenSlidesItem.title" tabindex="-1">
      <button class="library-slides-close" type="button" aria-label="Close fullscreen preview" @click="closeSlidesFullscreen">×</button>
      <SlidesPreview :title="fullscreenSlidesItem.title" :content="fullscreenSlidesItem.content" :show-fullscreen-button="false" auto-focus />
    </section>
  </Teleport>
</template>
