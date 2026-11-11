<script setup>
import { computed } from 'vue'
import { ErrorMessage, FormControl } from 'frappe-ui'
import { marketStore } from '../../../data/markets'

const props = defineProps({
  languages: { type: Array, required: true },
  defaultLanguage: { type: String, default: '' },
  readOnly: { type: Boolean, default: false },
  error: { type: String, default: '' },
})

const emit = defineEmits(['update:languages', 'update:defaultLanguage'])

const storefrontLanguages = computed(() => marketStore.choices.value?.languages ?? [])

const defaultOptions = computed(() =>
  props.languages.map((code) => ({ label: marketStore.languageName(code), value: code })),
)

// A market keeps a language that was unpublished after it was added, so it can still be dropped.
function canPick(language) {
  return language.published || props.languages.includes(language.code)
}

function toggle(code, isOn) {
  const languages = isOn ? [...props.languages, code] : props.languages.filter((language) => language !== code)
  emit('update:languages', languages)
}
</script>

<template>
  <section class="space-y-4">
    <h3 class="text-base font-semibold text-ink-gray-8">{{ __('Languages') }}</h3>
    <div>
      <div class="grid gap-2 sm:grid-cols-3">
        <FormControl
          v-for="language in storefrontLanguages"
          :key="language.code"
          type="checkbox"
          :label="language.name"
          :description="canPick(language) ? undefined : __('Publish it first')"
          :model-value="languages.includes(language.code)"
          :disabled="readOnly || !canPick(language)"
          @update:model-value="(isOn) => toggle(language.code, isOn)"
        />
      </div>
      <ErrorMessage v-if="error" class="mt-2" :message="error" />
    </div>
    <FormControl
      class="sm:w-72"
      type="select"
      :label="__('Default language')"
      :model-value="defaultLanguage"
      :options="defaultOptions"
      :disabled="readOnly || !languages.length"
      @update:model-value="(code) => emit('update:defaultLanguage', code)"
    />
  </section>
</template>
