<script setup>
/**
 * One provider, one row: the mark, what state it is in, and the two things you came to
 * do — turn it on, or give it keys. Every piece of state is the server's answer, never a
 * local flag, so a card cannot claim a connection the site does not have.
 */
import { computed } from 'vue'
import { Badge, Button, Switch } from 'frappe-ui'
import IntegrationLogo from '../integrations/IntegrationLogo.vue'

const props = defineProps({
  card: { type: Object, required: true },
  busy: { type: Boolean, default: false },
})

defineEmits(['configure', 'toggle'])

// Enabling through Commera is refused while a required field is blank (save_integration in
// api/admin/integrations.py), but a provider switched on in Desk or by a seed script reaches
// this screen enabled with its keys still empty. It cannot take a payment in that state, so
// the row must not carry a green "Live" beside the warning — the warning is the whole truth.
const needsKeys = computed(() => props.card.enabled && props.card.missing?.length > 0)
const isLive = computed(() => props.card.enabled && !needsKeys.value)
</script>

<template>
  <div class="flex items-center gap-3 py-3">
    <IntegrationLogo :slug="card.slug" :label="card.label" />

    <div class="min-w-0 flex-1">
      <div class="flex items-center gap-2">
        <p class="truncate text-base text-ink-gray-8">{{ card.label }}</p>
        <Badge v-if="isLive" label="Live" theme="green" variant="subtle" />
        <Badge v-else-if="needsKeys" label="Keys missing" theme="orange" variant="subtle" />
        <!-- The app behind this provider is not installed on the site, so there is
             nothing to configure and the row says so rather than offering keys. -->
        <Badge v-if="!card.available" label="Not installed" theme="gray" variant="subtle" />
      </div>
      <!-- Wraps rather than truncates: a carrier blurb is a sentence, and clipping it at the
           column edge cut it mid-word — which reads as a rendering fault rather than as text
           there is more of. The row grows instead; nothing below it is positioned absolutely. -->
      <p v-if="card.blurb" class="mt-1 text-sm text-ink-gray-5">{{ card.blurb }}</p>
    </div>

    <div class="ml-auto flex shrink-0 items-center gap-3">
      <Button
        :label="card.configured ? 'Configure' : 'Add keys'"
        :disabled="!card.available"
        @click="$emit('configure', card.slug)"
      />
      <Switch
        :model-value="card.enabled"
        size="sm"
        :disabled="!card.available || busy"
        @update:model-value="$emit('toggle', $event)"
      />
    </div>
  </div>
</template>

