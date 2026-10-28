<script setup>
/**
 * A provider's plate: its real logo where the registry has one, the image a plugin app
 * names as `logo`, else its letter on its own colour.
 *
 * The markup handed to `v-html` is composed entirely from `logos.js`'s own string
 * literals; the only server value that reaches it is the label, which is XML-escaped into
 * the accessible name and never into markup of its own.
 */
import { computed } from 'vue'
import { brandFor } from '../../data/integrations'
import { escapeXml, getIntegrationLogo } from './logos'

const props = defineProps({
  slug: { type: String, required: true },
  label: { type: String, default: '' },
  // An image URL from a plugin app's provider class. An <img>, never v-html.
  logo: { type: String, default: '' },
  // A provider row carries the full plate; a group heading inside a form wants a
  // smaller one, so the plate is not louder than the heading it belongs to.
  size: { type: String, default: 'md', validator: (value) => ['sm', 'md'].includes(value) },
})

const plateClass = computed(() => (props.size === 'sm' ? 'h-7 w-[4.5rem]' : 'h-9 w-24'))

const markup = computed(() => {
  const { plate } = brandFor(props.slug)
  return `<svg viewBox="0 0 112 40" width="100%" height="100%" preserveAspectRatio="xMidYMid meet" role="img" aria-label="${escapeXml(props.label)}" focusable="false"><rect width="112" height="40" rx="8" fill="${plate.background}" />${plate.svg}</svg>`
})
</script>

<template>
  <div
    v-if="logo && !getIntegrationLogo(slug)"
    class="shrink-0 overflow-hidden rounded-5 border border-outline-gray-2 bg-surface-base p-1.5"
    :class="plateClass"
  >
    <img :src="logo" :alt="label" class="h-full w-full object-contain" />
  </div>
  <div
    v-else
    class="shrink-0 overflow-hidden rounded-5 border border-outline-gray-2"
    :class="plateClass"
    v-html="markup"
  />
</template>
