<script setup>
import { computed } from 'vue'
import { Badge, Button, Dropdown, Switch } from 'frappe-ui'
import { __ } from '../../data/translation'

const props = defineProps({
  language: { type: Object, required: true },
  prefix: { type: String, required: true },
  isDefault: { type: Boolean, default: false },
  isFirst: { type: Boolean, default: false },
  isLast: { type: Boolean, default: false },
  canTranslate: { type: Boolean, default: false },
  busy: { type: Boolean, default: false },
})

const emit = defineEmits(['publish', 'preview', 'move', 'make-default', 'translate', 'remove'])

const menu = computed(() =>
  [
    props.canTranslate &&
      !props.isDefault && { label: __('Translate'), icon: 'lucide-book-a', onClick: () => emit('translate') },
    !props.isFirst && { label: __('Move up'), icon: 'lucide-arrow-up', onClick: () => emit('move', -1) },
    !props.isLast && { label: __('Move down'), icon: 'lucide-arrow-down', onClick: () => emit('move', 1) },
    !props.isDefault &&
      props.language.published && { label: __('Make default'), icon: 'lucide-star', onClick: () => emit('make-default') },
    !props.isDefault && { label: __('Remove'), icon: 'lucide-trash-2', theme: 'red', onClick: () => emit('remove') },
  ].filter(Boolean),
)
</script>

<template>
  <li class="flex items-center gap-3 py-2.5">
    <!-- min-w-0 lets a long name truncate instead of pushing the switch off the row. -->
    <div class="min-w-0 flex-1">
      <div class="flex min-w-0 items-center gap-2">
        <p class="truncate text-base text-ink-gray-8">{{ language.name }}</p>
        <span
          v-if="language.endonym !== language.name"
          class="truncate text-sm text-ink-gray-5"
          :dir="language.direction"
        >
          {{ language.endonym }}
        </span>
        <Badge v-if="isDefault" variant="subtle" theme="blue" :label="__('Default')" />
        <Badge v-if="language.direction === 'rtl'" variant="outline" theme="gray" :label="__('Right to left')" />
      </div>
      <p class="mt-0.5 truncate font-mono text-sm text-ink-gray-5" dir="ltr">{{ prefix }}</p>
    </div>

    <div class="flex shrink-0 items-center gap-1.5">
      <Button
        v-if="!language.published"
        variant="ghost"
        icon-left="lucide-external-link"
        :label="__('Preview')"
        @click="emit('preview')"
      />
      <Switch
        :model-value="Boolean(language.published)"
        :disabled="isDefault || busy"
        :aria-label="__('Publish {0}', [language.name])"
        @update:model-value="emit('publish', $event)"
      />
      <Dropdown :options="menu" align="end">
        <Button variant="ghost" icon="lucide-ellipsis" :aria-label="__('More actions for {0}', [language.name])" />
      </Dropdown>
    </div>
  </li>
</template>
