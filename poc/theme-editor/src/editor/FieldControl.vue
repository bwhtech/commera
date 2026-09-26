<script setup>
import { computed } from 'vue'
import { Popover, Select, Slider, Switch, Textarea, TextInput } from 'frappe-ui'
import { COLLECTIONS, FONTS, IMAGES, imageUrl } from '../theme/sample-data.js'

// One control per setting type. In Commera these types are docfield types, so
// this becomes the dashboard's SettingsFieldControl plus two new controls
// (colour and image picker); the prototype keeps it self-contained.
const props = defineProps({
  setting: { type: Object, required: true },
  value: { default: undefined },
  language: { type: String, required: true },
})
const emit = defineEmits(['change'])

const shown = computed(() => {
  if (!props.setting.translatable) return props.value
  return props.value?.[props.language] ?? ''
})

// A translatable field left empty in Arabic falls back to English on the
// storefront; showing that as the placeholder says so without a banner.
const placeholder = computed(() => (props.setting.translatable && props.language !== 'en' ? props.value?.en : ''))

const optionsFor = (setting) => {
  if (setting.options === 'fonts') return FONTS
  if (setting.type === 'collection') return COLLECTIONS.map(({ value, label }) => ({ value, label }))
  return setting.options
}

const change = (value) => emit('change', value)
</script>

<template>
  <div class="space-y-1.5" :data-field="setting.id">
    <div v-if="setting.type !== 'check'" class="flex items-center justify-between">
      <label class="text-sm text-ink-gray-7">{{ setting.label }}</label>
      <span
        v-if="setting.translatable"
        class="rounded bg-surface-gray-2 px-1.5 text-xs font-medium uppercase text-ink-gray-6"
        :title="`Editing the ${language === 'ar' ? 'Arabic' : 'English'} text`"
      >{{ language }}</span>
    </div>

    <TextInput
      v-if="setting.type === 'text'"
      :model-value="shown"
      :placeholder="placeholder"
      :dir="language === 'ar' && setting.translatable ? 'rtl' : 'ltr'"
      @update:model-value="change"
    />
    <Textarea
      v-else-if="setting.type === 'textarea'"
      :model-value="shown"
      :placeholder="placeholder"
      :rows="3"
      :dir="language === 'ar' && setting.translatable ? 'rtl' : 'ltr'"
      @update:model-value="change"
    />
    <Switch
      v-else-if="setting.type === 'check'"
      :model-value="Boolean(value)"
      :label="setting.label"
      @update:model-value="change"
    />
    <Select
      v-else-if="setting.type === 'select' || setting.type === 'collection'"
      class="w-full"
      :model-value="value"
      :options="optionsFor(setting)"
      :placeholder="setting.type === 'collection' ? 'Choose a collection' : undefined"
      @update:model-value="change"
    />
    <div v-else-if="setting.type === 'range'" class="flex items-center gap-3">
      <Slider
        class="flex-1"
        :model-value="[Number(value)]"
        :min="setting.min"
        :max="setting.max"
        :step="setting.step"
        @update:model-value="(values) => change(values?.[0])"
      />
      <span class="w-10 text-right text-sm tabular-nums text-ink-gray-7">{{ value }}{{ setting.unit ?? '' }}</span>
    </div>
    <div v-else-if="setting.type === 'color'" class="flex items-center gap-2">
      <!-- A merchant's colour is data, not styling: the native picker holds it. -->
      <input
        type="color"
        class="h-7 w-9 cursor-pointer rounded border border-outline-gray-2 bg-transparent"
        :value="value"
        @input="change($event.target.value)"
      />
      <TextInput class="flex-1" :model-value="value" @update:model-value="change" />
    </div>
    <Popover v-else-if="setting.type === 'image'" side="bottom" align="start">
      <template #trigger>
        <button class="w-full overflow-hidden rounded border border-outline-gray-2 text-left hover:border-outline-gray-3">
          <img :src="imageUrl(value)" alt="" class="h-24 w-full object-cover" />
          <span class="block px-2 py-1.5 text-sm text-ink-gray-7">Change image</span>
        </button>
      </template>
      <div class="grid w-72 grid-cols-2 gap-2 p-2">
        <button
          v-for="image in IMAGES"
          :key="image.value"
          class="overflow-hidden rounded border-2"
          :class="image.value === value ? 'border-outline-gray-5' : 'border-transparent'"
          @click="change(image.value)"
        >
          <img :src="image.url" :alt="image.label" class="h-16 w-full object-cover" />
        </button>
      </div>
    </Popover>
  </div>
</template>
