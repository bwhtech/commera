<script setup>
import { computed } from 'vue'
import { Badge, Button, Dropdown } from 'frappe-ui'
import { ruleSummary } from '../../data/shippingRates'
import { __ } from '../../data/translation'

const props = defineProps({
  rule: { type: Object, required: true },
  inUse: { type: Boolean, default: false },
  optionTitles: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['edit', 'use', 'delete'])

const summary = computed(() => ruleSummary(props.rule.bands, props.optionTitles) || __('No bands yet'))

const actions = computed(() => [
  ...(props.inUse
    ? []
    : [{ label: __('Use at checkout'), icon: 'lucide-circle-check', onClick: () => emit('use', props.rule) }]),
  {
    label: __('Delete'),
    icon: 'lucide-trash-2',
    theme: 'red',
    disabled: props.inUse,
    description: props.inUse ? __('Checkout uses this rule') : undefined,
    onClick: () => emit('delete', props.rule),
  },
])
</script>

<template>
  <div class="flex items-center gap-3 py-3">
    <div class="min-w-0 flex-1">
      <div class="flex items-center gap-2">
        <p class="truncate text-base" :class="rule.disabled ? 'text-ink-gray-5' : 'text-ink-gray-8'">
          {{ rule.label }}
        </p>
        <Badge v-if="inUse" :label="__('In use')" theme="green" variant="subtle" />
        <Badge v-if="rule.disabled" :label="__('Off')" theme="gray" variant="subtle" />
      </div>
      <p class="mt-1 truncate text-sm text-ink-gray-5">{{ summary }}</p>
    </div>

    <div class="ms-auto flex shrink-0 items-center gap-2">
      <Button :label="__('Edit')" @click="emit('edit', rule)" />
      <Dropdown :options="actions">
        <Button icon="lucide-ellipsis" :aria-label="__('More actions for {0}', [rule.label])" />
      </Dropdown>
    </div>
  </div>
</template>
