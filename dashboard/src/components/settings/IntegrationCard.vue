<script setup>
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
    <IntegrationLogo :slug="card.slug" :label="card.label" :logo="card.logo ?? ''" />

    <div class="min-w-0 flex-1">
      <div class="flex items-center gap-2">
        <p class="truncate text-base text-ink-gray-8">{{ card.label }}</p>
        <Badge v-if="isLive" :label="__('Live')" theme="green" variant="subtle" />
        <Badge v-else-if="needsKeys" :label="__('Keys missing')" theme="amber" variant="subtle" />
        <!-- The app behind this provider is not installed on the site, so there is
             nothing to configure and the row says so rather than offering keys. -->
        <Badge v-if="!card.available" :label="__('Not installed')" theme="gray" variant="subtle" />
      </div>
    </div>

    <div class="ms-auto flex shrink-0 items-center gap-3">
      <Button
        v-if="card.available && (card.enabled || card.configured)"
        :label="__('Configure')"
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

