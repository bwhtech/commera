<script setup>
import { computed, ref, watch } from 'vue'
import { useDebounceFn } from '@vueuse/core'
import { Button } from 'frappe-ui'
import SettingsFieldControl from '../settings/SettingsFieldControl.vue'
import { sectionSettingToField } from '../../utils/sectionSettingToField'
import { isTranslatable, maxProducts } from '../../data/themeLayout'

const props = defineProps({
  editor: { type: Object, required: true },
})

const { state, selected, select, settingValue, settingPlaceholder, setSetting, commit, toggleHidden } =
  props.editor
const { removeSection, removeBlock, saveThemeSetting } = props.editor

const fields = computed(() => {
  const current = selected.value
  if (!current?.schema) return []
  return (current.schema.settings ?? []).map((setting) => {
    const field = sectionSettingToField(setting)
    if (setting.type === 'products') {
      field.max_products = maxProducts(current.sectionSchema)
      field.description = `Pick up to ${field.max_products}.`
    }
    field.placeholder = settingPlaceholder(current.owner, setting)
    return { setting, field }
  })
})

function back() {
  const current = selected.value
  if (current?.kind === 'block') select({ kind: 'section', group: current.group, section: current.section.id })
  else select(null)
}

function remove() {
  const current = selected.value
  if (current.kind === 'block') removeBlock(current.group, current.section.id, current.block.id)
  else removeSection(current.group, current.section.id)
}

const TYPING_PAUSE_MS = 400
const renderAfterTyping = useDebounceFn(commit, TYPING_PAUSE_MS)

function update(setting, value) {
  setSetting(selected.value.owner, setting, value)
  if (isTranslatable(setting)) renderAfterTyping()
}

function settle(setting, value) {
  setSetting(selected.value.owner, setting, value)
  commit()
}

const themeValues = ref({})
watch(
  () => state.settings,
  (settings) => {
    themeValues.value = Object.fromEntries(
      (settings.groups ?? []).flatMap((group) =>
        group.fields.map((field) => [field.fieldname, field.value ?? '']),
      ),
    )
  },
  { immediate: true },
)

async function saveTheme(field, value) {
  if (!(await saveThemeSetting(field, value))) themeValues.value[field.fieldname] = field.value ?? ''
}

function plainText(html) {
  if (!html) return ''
  const element = document.createElement('div')
  element.innerHTML = html
  return element.textContent.replace(/\s+/g, ' ').trim()
}
</script>

<template>
  <div v-if="selected?.kind === 'theme'" class="flex h-full flex-col" data-settings-panel>
    <div class="border-b border-outline-gray-2 px-4 py-3">
      <div class="flex items-center gap-1">
        <Button variant="ghost" icon="lucide-arrow-left" aria-label="Back" @click="select(null)" />
        <h2 class="min-w-0 flex-1 truncate text-lg-semibold text-ink-gray-9">Theme settings</h2>
      </div>
      <p v-if="state.live" class="mt-1 text-p-sm text-ink-gray-5">
        These apply to every page of your store as soon as you change them. Publish is not needed.
      </p>
      <p v-else class="mt-1 text-p-sm text-ink-gray-5">Activate {{ state.theme }} to change its settings.</p>
    </div>

    <div class="min-h-0 flex-1 overflow-y-auto px-4 py-4">
      <p v-if="!state.settings.groups?.length" class="text-p-sm text-ink-gray-5">
        This theme ships no settings of its own.
      </p>
      <div v-for="group in state.settings.groups" :key="group.label" class="mb-6">
        <p class="text-sm text-ink-gray-5">{{ group.label }}</p>
        <div class="mt-2 flex flex-col gap-4">
          <div v-for="field in group.fields" :key="field.fieldname">
            <label class="mb-1.5 block text-base text-ink-gray-6" :for="`theme-${field.fieldname}`">
              {{ field.label }}
            </label>
            <SettingsFieldControl
              :id="`theme-${field.fieldname}`"
              v-model="themeValues[field.fieldname]"
              :class="field.fieldtype === 'Check' ? undefined : '!w-full'"
              :field="field"
              :disabled="!state.live || editor.busy.value"
              @change="saveTheme(field, $event)"
            />
            <p v-if="plainText(field.description)" class="mt-1 text-sm text-ink-gray-5">
              {{ plainText(field.description) }}
            </p>
          </div>
        </div>
      </div>
    </div>
  </div>

  <div v-else-if="selected" class="flex h-full flex-col" data-settings-panel>
    <div class="border-b border-outline-gray-2 px-4 py-3">
      <div class="flex items-center gap-1">
        <Button
          variant="ghost"
          icon="lucide-arrow-left"
          :aria-label="selected.kind === 'block' ? `Back to ${selected.sectionSchema.name}` : 'Back'"
          @click="back"
        />
        <h2 class="min-w-0 flex-1 truncate text-lg-semibold text-ink-gray-9">{{ selected.schema.name }}</h2>
        <Button
          v-if="selected.kind === 'section'"
          variant="ghost"
          :icon="selected.section.hidden ? 'lucide-eye-off' : 'lucide-eye'"
          :aria-label="selected.section.hidden ? 'Show section' : 'Hide section'"
          @click="toggleHidden(selected.group, selected.section.id)"
        />
        <Button variant="ghost" icon="lucide-trash-2" :aria-label="`Remove ${selected.kind}`" @click="remove" />
      </div>
      <p v-if="selected.kind === 'block'" class="mt-1 text-sm text-ink-gray-5">
        In {{ selected.sectionSchema.name }}
      </p>
      <p v-else-if="selected.section.hidden" class="mt-1 text-sm text-ink-gray-5">
        Hidden. It stays in the layout but the store does not show it.
      </p>
    </div>

    <div class="min-h-0 flex-1 overflow-y-auto px-4 py-4">
      <p v-if="!fields.length" class="text-p-sm text-ink-gray-5">
        This {{ selected.kind }} has no settings. Drag it in the list to move it.
      </p>
      <div class="flex flex-col gap-4">
        <div v-for="{ setting, field } in fields" :key="`${state.language}:${field.fieldname}`">
          <label class="mb-1.5 block text-base text-ink-gray-6" :for="`setting-${field.fieldname}`">
            {{ field.label }}
          </label>
          <SettingsFieldControl
            :id="`setting-${field.fieldname}`"
            :model-value="settingValue(selected.owner, setting)"
            :class="field.fieldtype === 'Check' ? undefined : '!w-full'"
            :field="field"
            :dir="isTranslatable(setting) && state.language === 'ar' ? 'rtl' : undefined"
            @update:model-value="update(setting, $event)"
            @change="settle(setting, $event)"
          />
          <p v-if="field.description" class="mt-1 text-sm text-ink-gray-5">{{ field.description }}</p>
        </div>
      </div>
    </div>
  </div>

  <div v-else class="flex h-full flex-col items-center justify-center gap-2 px-6 text-center">
    <span class="lucide-mouse-pointer-click size-6 text-ink-gray-4" aria-hidden="true" />
    <p class="text-base text-ink-gray-7">Select a section</p>
    <p class="text-p-sm text-ink-gray-5">Click it in the preview or in the list to change its settings.</p>
  </div>
</template>
