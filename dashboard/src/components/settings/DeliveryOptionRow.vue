<script setup>
/**
 * One delivery option, as the shopper will meet it: the name they read at checkout, what
 * it costs them, and where the price comes from. The switch is the only thing on the row
 * an owner reaches for daily, so it sits furthest right, past the two rarer actions.
 */
import { computed } from 'vue'
import { Badge, Button, Dropdown, Switch } from 'frappe-ui'
import { money } from '../../data/format'

const props = defineProps({
  option: { type: Object, required: true },
  busy: { type: Boolean, default: false },
})

defineEmits(['edit', 'delete', 'toggle'])

// Where the price comes from, in the order the server applies it. A rate the carrier
// quotes live is the interesting case: everything else is a fixed number the owner typed.
const priceParts = computed(() => {
  const parts = []

  if (props.option.shipping_rule) parts.push(props.option.shipping_rule)
  else if (props.option.service_code) parts.push('Carrier rate')

  if (props.option.markup_percent) parts.push(`+${props.option.markup_percent}%`)
  if (props.option.handling_fee) parts.push(`+${money(props.option.handling_fee)} handling`)
  // What the shopper is charged when the carrier will not quote — the difference between
  // a checkout that completes and one that dead-ends, so it is never hidden behind Edit.
  // With no carrier there is no live rate to fall back from, so the backup charge is the price.
  if (props.option.backup_charge) {
    parts.push(
      props.option.provider
        ? `${money(props.option.backup_charge)} fallback`
        : `${money(props.option.backup_charge)} flat`,
    )
  }

  return parts
})

const source = computed(() => props.option.carrier || props.option.provider || 'Own delivery')

// Frappe answers 1/0. Handed straight to a Switch, reka never reads a non-boolean as its
// starting state: the thumb renders on from `data-state` while its internal value stays
// false, so the first click emits `true` on an option that is already on and the row will
// not switch off at all.
const isOn = computed(() => Boolean(props.option.enabled))
</script>

<template>
  <div class="flex items-center gap-3 py-3">
    <div class="min-w-0 flex-1">
      <div class="flex items-center gap-2">
        <p class="truncate text-base text-ink-gray-8">{{ option.title }}</p>
        <Badge v-if="source" :label="source" theme="gray" variant="subtle" />
      </div>
      <p v-if="option.description" class="mt-1 truncate text-sm text-ink-gray-5">
        {{ option.description }}
      </p>
      <p v-if="priceParts.length" class="mt-1 truncate text-sm text-ink-gray-5">
        {{ priceParts.join(' · ') }}
      </p>
    </div>

    <div class="ml-auto flex shrink-0 items-center gap-2">
      <Button label="Edit" @click="$emit('edit', option)" />
      <Dropdown
        :options="[
          {
            label: 'Delete',
            icon: 'lucide-trash-2',
            theme: 'red',
            onClick: () => $emit('delete', option),
          },
        ]"
      >
        <Button icon="lucide-ellipsis" :aria-label="`More actions for ${option.title}`" />
      </Dropdown>
      <Switch
        :model-value="isOn"
        size="sm"
        :disabled="busy"
        @update:model-value="$emit('toggle', $event)"
      />
    </div>
  </div>
</template>
