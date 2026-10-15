<script setup lang="ts">
import { defineAsyncComponent } from 'vue'
import { libraryClient } from '../api/client'
import { libraryPdfLaunch } from '../app/library/state'

const PdfPreview = defineAsyncComponent(() => import('../components/PdfPreview.vue'))
</script>

<template>
  <div v-if="libraryPdfLaunch" class="library-pdf-launch">
    <PdfPreview
      :asset="libraryClient.documentReference(libraryPdfLaunch.item.id)"
      artifact
      :initial-mode="libraryPdfLaunch.mode"
      @close="libraryPdfLaunch = null"
    />
  </div>
</template>
