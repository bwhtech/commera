<script setup>
import { computed } from 'vue'
import { Button } from 'frappe-ui'
import { APP_BLOCKS, SECTIONS } from '../theme/schemas.js'
import FieldControl from './FieldControl.vue'

const props = defineProps({ editor: { type: Object, required: true } })
const { state, selection, selectedSchema, setValue, remove, toggleHidden, select } = props.editor

const app = computed(() => (selection.value?.kind === 'block' ? APP_BLOCKS[selection.value.node.type]?.app : null))
const parentSection = computed(() => (selection.value?.kind === 'block' ? selection.value.section : null))
</script>

<template>
  <div v-if="!selection || !selectedSchema" class="flex h-full flex-col items-center justify-center gap-2 px-6 text-center">
    <span class="lucide-mouse-pointer-click size-6 text-ink-gray-4" aria-hidden="true" />
    <p class="text-base text-ink-gray-7">Select a section or block</p>
    <p class="text-sm text-ink-gray-5">Click it in the preview or in the list on the left to change its settings.</p>
  </div>

  <div v-else class="flex h-full flex-col" data-settings-panel>
    <div class="border-b border-outline-gray-2 px-4 py-3">
      <button
        v-if="parentSection"
        class="mb-1 flex items-center gap-1 text-sm text-ink-gray-5 hover:text-ink-gray-7"
        @click="select(parentSection.id)"
      >
        <span class="lucide-chevron-left size-3.5" aria-hidden="true" />
        {{ SECTIONS[parentSection.type].name }}
      </button>
      <div class="flex items-center gap-2">
        <span :class="selectedSchema.icon" class="size-4 text-ink-gray-6" aria-hidden="true" />
        <h2 class="min-w-0 flex-1 truncate text-lg font-semibold text-ink-gray-9">{{ selectedSchema.name }}</h2>
        <template v-if="selection.kind !== 'theme'">
          <Button
            size="sm"
            variant="ghost"
            :icon="selection.node.disabled ? 'lucide-eye-off' : 'lucide-eye'"
            :label="selection.node.disabled ? 'Show' : 'Hide'"
            @click="toggleHidden(selection.node.id)"
          />
          <Button
            v-if="!selectedSchema.static"
            size="sm"
            variant="ghost"
            icon="lucide-trash-2"
            label="Remove"
            @click="remove(selection.node.id)"
          />
        </template>
      </div>
      <p v-if="app" class="mt-1 text-sm text-ink-gray-6">
        App block from <span class="font-medium text-ink-violet-4">{{ app }}</span>. The theme only decides where it may go.
      </p>
      <p v-else-if="selectedSchema.static" class="mt-1 text-sm text-ink-gray-6">This section is part of the page and can't be removed.</p>
    </div>

    <div class="min-h-0 flex-1 space-y-5 overflow-y-auto px-4 py-4">
      <FieldControl
        v-for="setting in selectedSchema.settings"
        :key="`${state.selectedId}:${setting.id}`"
        :setting="setting"
        :value="selection.node.settings[setting.id]"
        :language="state.language"
        @change="(value) => setValue(setting.id, value, setting.translatable)"
      />
      <p v-if="!selectedSchema.settings.length" class="text-sm text-ink-gray-5">This block has no settings; drag it in the list to move it.</p>
    </div>
  </div>
</template>
