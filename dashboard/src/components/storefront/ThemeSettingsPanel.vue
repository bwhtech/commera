<script setup>
import { computed, ref, watch } from 'vue'
import { Button, FormLabel, ScrollArea } from 'frappe-ui'
import SettingsFieldControl from '../settings/SettingsFieldControl.vue'

const props = defineProps({
  editor: { type: Object, required: true },
})

const emit = defineEmits(['close', 'dirty'])

const { state, saveThemeSettings } = props.editor

const values = ref({})
const saving = ref(false)

const fields = computed(() => (state.settings.groups ?? []).flatMap((group) => group.fields))

watch(
  () => state.settings,
  () => {
    values.value = Object.fromEntries(fields.value.map((field) => [field.fieldname, field.value ?? '']))
  },
  { immediate: true },
)

const changes = computed(() =>
  Object.fromEntries(
    fields.value
      .filter((field) => values.value[field.fieldname] !== (field.value ?? ''))
      .map((field) => [field.fieldname, values.value[field.fieldname]]),
  ),
)

const isDirty = computed(() => Object.keys(changes.value).length > 0)
watch(isDirty, (dirty) => emit('dirty', dirty), { immediate: true })

async function save() {
  saving.value = true
  try {
    await saveThemeSettings(changes.value)
  } finally {
    saving.value = false
  }
}

function plainText(html) {
  if (!html) return ''
  const element = document.createElement('div')
  element.innerHTML = html
  return element.textContent.replace(/\s+/g, ' ').trim()
}
</script>

<template>
  <div class="flex h-full flex-col" data-theme-settings-panel>
    <div class="shrink-0 border-b border-outline-gray-2 px-4 py-2">
      <div class="flex items-center gap-1">
        <h2 class="min-w-0 flex-1 truncate text-lg-semibold text-ink-gray-9">{{ __('Theme settings') }}</h2>
        <Button variant="ghost" icon="lucide-x" :aria-label="__('Close theme settings')" @click="emit('close')" />
      </div>
    </div>

    <ScrollArea class="min-h-0 flex-1" viewport-class="p-4">
      <p v-if="!state.live" class="mb-6 text-p-sm text-ink-gray-5">
        {{ __('Activate {0} to change its settings.', [state.theme]) }}
      </p>
      <p v-if="!state.settings.groups?.length" class="text-p-sm text-ink-gray-5">
        {{ __('This theme ships no settings of its own.') }}
      </p>
      <div class="flex flex-col gap-6">
        <section v-for="group in state.settings.groups" :key="group.label" class="flex flex-col gap-3">
          <h4 class="text-xs text-ink-gray-5">{{ group.label }}</h4>
          <div v-for="field in group.fields" :key="field.fieldname" class="flex flex-col gap-1.5">
            <FormLabel :id="`theme-${field.fieldname}`" :label="field.label" />
            <SettingsFieldControl
              :id="`theme-${field.fieldname}`"
              v-model="values[field.fieldname]"
              :class="field.fieldtype === 'Check' ? undefined : '!w-full'"
              :field="field"
              :disabled="!state.live || saving"
            />
            <p v-if="plainText(field.description)" class="text-xs text-ink-gray-5">
              {{ plainText(field.description) }}
            </p>
          </div>
        </section>
      </div>
    </ScrollArea>

    <div class="shrink-0 border-t border-outline-gray-2 p-4">
      <Button class="w-full" variant="solid" :label="__('Save')" :disabled="!isDirty || saving" :loading="saving" @click="save" />
    </div>
  </div>
</template>
