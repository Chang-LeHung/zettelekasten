<script setup lang="ts">
import { notice, noticeKind } from '../app/notice'
</script>

<template>
  <Transition name="toast">
    <div v-if="notice" class="toast" :class="noticeKind" role="status">
      <svg v-if="noticeKind === 'success'"><use href="#icon-check" /></svg>
      <span>{{ notice }}</span>
    </div>
  </Transition>
</template>
