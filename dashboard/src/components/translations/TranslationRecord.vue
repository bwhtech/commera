<script setup>
import { computed } from 'vue'
import { Badge, Button } from 'frappe-ui'
import TranslationField from './TranslationField.vue'
import { fieldKey, groupSections } from '../../data/translationStatus'

// One record's fields in cards. A change carries this record, read from the prop: a field that
// emits as it unmounts still names the record it belonged to, not the one opened next.
const props = defineProps({
  item: { type: Object, required: true },
  resourceType: { type: String, required: true },
  // The resource's name for one record, e.g. "Product".
  resourceName: { type: String, required: true },
  language: { type: Object, required: true },
  sourceLanguage: { type: Object, required: true },
  // Unsaved values by fieldKey().
  pending: { type: Object, required: true },
  disabled: { type: Boolean, default: false },
  showBack: { type: Boolean, default: false },
})
const emit = defineEmits(['change', 'back'])

const sections = computed(() => groupSections(props.item.fields, props.resourceName))

function viewOnStore() {
  window.open(props.item.url, '_blank', 'noopener')
}
</script>

<template>
  <div>
    <div class="flex flex-wrap items-center gap-2">
      <Button
        v-if="showBack"
        :disabled="disabled"
        variant="ghost"
        icon="lucide-arrow-left"
        class="rtl:-scale-x-100"
        :label="__('All items')"
        @click="emit('back')"
      />
      <h2 class="min-w-0 truncate text-lg-semibold text-ink-gray-9">{{ item.title }}</h2>
      <Badge variant="outline" theme="gray" :label="resourceName" />
      <Button
        v-if="item.url"
        class="ms-auto"
        icon-left="lucide-external-link"
        :label="__('View on store')"
        @click="viewOnStore"
      />
    </div>

    <section
      v-for="section in sections"
      :key="section.title"
      class="mt-5 overflow-hidden rounded-5 border border-outline-gray-2"
    >
      <h3 class="px-4 pb-2.5 pt-3 text-base-semibold text-ink-gray-8">{{ section.title }}</h3>
      <div
        class="hidden grid-cols-[11rem_minmax(0,1fr)_minmax(0,1fr)] border-y border-outline-gray-1 text-sm text-ink-gray-5 sm:grid"
      >
        <span />
        <span class="px-4 py-2">{{ sourceLanguage.name }}</span>
        <span class="px-4 py-2">{{ language.name }}</span>
      </div>
      <div class="divide-y divide-outline-gray-1 max-sm:border-t max-sm:border-outline-gray-1">
        <TranslationField
          v-for="field in section.fields"
          :key="field.field"
          :field="field"
          :language="language"
          :source-language="sourceLanguage"
          :record-title="item.title"
          :disabled="disabled"
          :pending="pending[fieldKey(language.code, resourceType, item.name, field.field)]"
          @change="(value) => emit('change', item, field, value)"
        />
      </div>
    </section>
  </div>
</template>
