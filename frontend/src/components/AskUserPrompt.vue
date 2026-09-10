<script setup lang="ts">
const props = defineProps<{
  question: string
  options: string[]
  allowMultiple: boolean
  selectedOptions: string[]
  answer: string
  submitting: boolean
}>()

const emit = defineEmits<{
  toggle: [option: string]
  'update:answer': [value: string]
  submit: []
}>()

function optionLetter(index: number): string {
  return String.fromCharCode('A'.charCodeAt(0) + index)
}

function updateAnswer(event: Event): void {
  emit('update:answer', (event.target as HTMLInputElement).value)
}
</script>

<template>
  <section class="ask-user" aria-live="polite">
    <header>
      <div>
        <span>Agent question</span>
        <small>{{ allowMultiple ? 'Select one or more options' : 'Select one option' }}</small>
      </div>
      <span class="waiting"><i />Waiting for you</span>
    </header>

    <h3>{{ question }}</h3>

    <form @submit.prevent="emit('submit')">
      <fieldset>
        <legend class="sr-only">{{ allowMultiple ? 'Select all that apply' : 'Select one answer' }}</legend>
        <label
          v-for="(option, index) in options"
          :key="`${index}-${option}`"
          class="ask-choice"
          :class="{ selected: selectedOptions.includes(option) }"
        >
          <input
            :type="allowMultiple ? 'checkbox' : 'radio'"
            name="agent-question"
            :checked="selectedOptions.includes(option)"
            @change="emit('toggle', option)"
          />
          <span class="choice-letter">{{ optionLetter(index) }}</span>
          <span class="choice-text">{{ option }}</span>
          <span class="choice-control" aria-hidden="true"><i /></span>
        </label>

        <label class="ask-choice custom" :class="{ selected: answer.trim() }">
          <span class="choice-letter">{{ optionLetter(options.length) }}</span>
          <span class="choice-text">
            <strong>Other</strong>
            <input
              :value="answer"
              type="text"
              :placeholder="options.length ? 'Enter a different answer…' : 'Type your answer…'"
              aria-label="Custom answer"
              @input="updateAnswer"
            />
          </span>
          <span class="choice-control" aria-hidden="true"><i /></span>
        </label>
      </fieldset>

      <footer>
        <small>{{ allowMultiple ? 'You may combine choices with your own answer.' : 'Choose one option or enter your own answer.' }}</small>
        <button type="submit" :disabled="submitting || (!answer.trim() && !selectedOptions.length)">
          {{ submitting ? 'Sending…' : 'Continue' }}
        </button>
      </footer>
    </form>
  </section>
</template>

<style scoped>
.ask-user { margin: .55rem .8rem 0; padding: .9rem; border: 1px solid rgba(71,105,87,.16); border-radius: .9rem; background: #f8faf8; box-shadow: 0 3px 14px rgba(42,65,51,.045); }
header, header > div, footer { display: flex; align-items: center; }
header { justify-content: space-between; gap: 1rem; }
header > div { align-items: baseline; gap: .45rem; }
header div > span { color: #3f624e; font-size: .67rem; font-weight: 740; letter-spacing: .025em; }
header small, footer small { color: #858e88; font-size: .59rem; }
.waiting { display: inline-flex; align-items: center; gap: .35rem; color: #738078; font-size: .58rem; }
.waiting i { width: .36rem; height: .36rem; border-radius: 50%; background: #65a67d; box-shadow: 0 0 0 3px rgba(101,166,125,.1); }
h3 { margin: .62rem 0 .72rem; color: #252a27; font-size: .84rem; font-weight: 650; line-height: 1.5; }
fieldset { display: grid; gap: .35rem; min-width: 0; margin: 0; padding: 0; border: 0; }
.ask-choice { display: grid; grid-template-columns: 1.75rem minmax(0,1fr) 1rem; align-items: center; gap: .55rem; min-height: 2.65rem; padding: .35rem .7rem .35rem .45rem; border: 1px solid #e0e6e2; border-radius: .68rem; color: #505b54; background: rgba(255,255,255,.88); cursor: pointer; transition: border-color 120ms ease, background 120ms ease, box-shadow 120ms ease; }
.ask-choice:hover { border-color: #b9c9bf; background: #fff; }
.ask-choice.selected { border-color: #87a593; color: #294d39; background: #edf4ef; box-shadow: inset 0 0 0 1px rgba(71,105,87,.06); }
.ask-choice > input { position: absolute; width: 1px; height: 1px; opacity: 0; pointer-events: none; }
.choice-letter { width: 1.75rem; height: 1.75rem; display: grid; place-items: center; border: 1px solid #d8e0db; border-radius: .5rem; color: #657269; background: #f4f7f5; font-size: .63rem; font-weight: 750; }
.selected .choice-letter { border-color: #88a593; color: #315541; background: #fff; }
.choice-text { min-width: 0; font-size: .69rem; line-height: 1.4; }
.choice-control { width: .82rem; height: .82rem; display: grid; place-items: center; border: 1.5px solid #bdc8c1; border-radius: 50%; background: #fff; }
.ask-user:has(input[type='checkbox']) .choice-control { border-radius: .25rem; }
.selected .choice-control { border-color: #547b64; background: #547b64; }
.selected .choice-control i { width: .28rem; height: .48rem; margin-top: -.08rem; border: solid white; border-width: 0 1.5px 1.5px 0; transform: rotate(45deg); }
.custom { align-items: start; }
.custom .choice-letter, .custom .choice-control { margin-top: .12rem; }
.custom .choice-text strong { display: block; margin-bottom: .18rem; color: #56625a; font-size: .65rem; }
.custom input { width: 100%; padding: 0; border: 0; outline: 0; color: #252a27; background: transparent; font: inherit; }
.custom input::placeholder { color: #a1a8a3; }
footer { justify-content: space-between; gap: 1rem; margin-top: .65rem; }
footer button { min-height: 2rem; padding: 0 .8rem; border: 0; border-radius: .62rem; color: #fff; background: #476957; cursor: pointer; font-size: .68rem; font-weight: 680; }
footer button:hover:not(:disabled) { background: #395b48; }
footer button:disabled { opacity: .42; cursor: default; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }
@media (max-width: 620px) {
  header { align-items: flex-start; }
  header > div { display: grid; gap: .15rem; }
  footer { align-items: flex-end; }
}
</style>
