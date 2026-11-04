<script setup>
import { computed, ref } from 'vue'
import { Button, toast } from 'frappe-ui'
import { webhookActions } from '../../../data/webhooks'

const props = defineProps({
  name: { type: String, required: true },
  hint: { type: String, default: '' },
})

// The plain secret, once the server has handed it over; null while only its hint is known.
const secret = defineModel('secret', { type: String, default: null })
const isShown = defineModel('shown', { type: Boolean, default: false })

const revealing = ref(false)
const shownText = computed(() => (isShown.value && secret.value ? secret.value : `whsec_${'•'.repeat(24)}${props.hint}`))

async function fetchSecret() {
  if (secret.value) return secret.value
  revealing.value = true
  const answer = await webhookActions.call('reveal_secret', { name: props.name })
  revealing.value = false
  if (answer) secret.value = answer.secret
  return secret.value
}

async function toggle() {
  if (isShown.value) {
    isShown.value = false
    return
  }
  if (await fetchSecret()) isShown.value = true
}

async function copy() {
  const value = await fetchSecret()
  if (!value) return
  await navigator.clipboard.writeText(value)
  toast.success('Secret copied')
}
</script>

<template>
  <div>
    <span class="text-sm text-ink-gray-6">Signing secret</span>
    <div class="mt-1.5 flex items-center gap-2">
      <code class="min-w-0 flex-1 truncate rounded-4 bg-surface-gray-2 px-2.5 py-1.5 font-mono text-sm text-ink-gray-8">
        {{ shownText }}
      </code>
      <Button
        :icon="isShown ? 'lucide-eye-off' : 'lucide-eye'"
        :label="isShown ? 'Hide secret' : 'Show secret'"
        :disabled="revealing"
        @click="toggle"
      />
      <Button icon="lucide-copy" label="Copy secret" @click="copy" />
    </div>
  </div>
</template>
