<script setup>
import { Checkbox } from 'frappe-ui'
import { webhookStore } from '../../../data/webhooks'

const selected = defineModel({ type: Array, required: true })

const groups = webhookStore.eventGroups

function toggle(event, isOn) {
  selected.value = isOn ? [...selected.value, event] : selected.value.filter((name) => name !== event)
}

function isGroupSelected(group) {
  return group.events.every((event) => selected.value.includes(event.event))
}

function toggleGroup(group) {
  const names = group.events.map((event) => event.event)
  selected.value = isGroupSelected(group)
    ? selected.value.filter((name) => !names.includes(name))
    : [...new Set([...selected.value, ...names])]
}
</script>

<template>
  <div class="space-y-5">
    <section v-for="group in groups" :key="group.label">
      <div class="flex items-center justify-between">
        <h4 class="text-sm text-ink-gray-5">{{ group.label }}</h4>
        <button type="button" class="rounded-1 text-sm text-ink-gray-6 hover:text-ink-gray-8" @click="toggleGroup(group)">
          {{ isGroupSelected(group) ? 'Clear' : 'Select all' }}
        </button>
      </div>
      <div class="mt-1.5 grid gap-x-6 sm:grid-cols-2">
        <label
          v-for="event in group.events"
          :key="event.event"
          class="flex cursor-pointer items-start gap-2.5 rounded-4 px-1.5 py-2 hover:bg-surface-gray-1"
        >
          <Checkbox
            class="mt-0.5"
            :model-value="selected.includes(event.event)"
            @update:model-value="(isOn) => toggle(event.event, isOn)"
          />
          <span class="min-w-0">
            <span class="block text-base text-ink-gray-8">{{ event.label }}</span>
            <span class="block text-p-xs text-ink-gray-5">{{ event.description }}</span>
            <code class="mt-0.5 block font-mono text-2xs text-ink-gray-4">{{ event.event }}</code>
          </span>
        </label>
      </div>
    </section>
  </div>
</template>
