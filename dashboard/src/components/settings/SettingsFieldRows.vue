<script setup>
/**
 * A group of docfields as settings rows, in the order the doctype itself lays them out.
 *
 * There is one of these in the app, not one per screen: the provider config, the analytics tab
 * and the advanced tab all render server-described fields, so a docfield's label, description,
 * required flag and "this secret is already stored" wording reach all three the same way.
 */
import { SettingsRow } from 'frappe-ui'
import SettingsFieldControl from './SettingsFieldControl.vue'
import IntegrationLogo from '../integrations/IntegrationLogo.vue'

const props = defineProps({
  groups: { type: Array, required: true },
  values: { type: Object, required: true },
  linkOptionsPath: { type: String, default: '' },
})

// `update` is every edit; `commit` is the value settled, for a screen that saves each field
// on its own rather than behind a Save button.
const emit = defineEmits(['update', 'commit'])

// Docfield descriptions are authored as Desk HTML — <b>…</b>, and entities like &gt;. A row
// interpolates its description as text, so the markup is unwrapped here rather than shown to the
// owner literally. Parsed in a detached element and read back as text: nothing is ever injected.
function plainText(html) {
  if (!html) return undefined

  const element = document.createElement('div')
  element.innerHTML = html
  return element.textContent.replace(/\s+/g, ' ').trim()
}

// A group led by a switch — an analytics service the store either reports to or does not —
// keeps its fields hidden until it is on: ids and credentials are only worth asking for once
// the thing that uses them is switched on.
function groupFields(group) {
  if (group.toggle && !isOn(group.toggle)) return []
  return group.fields
}

function isOn(field) {
  const value = props.values[field.fieldname]
  return Boolean(value) && value !== '0'
}

// A secret already stored is the one thing this screen cannot show, so it says so instead.
function hint(field) {
  if (field.is_secret && field.is_set) return 'Stored. Leave blank to keep it.'
  if (field.is_secret) return 'Stored encrypted, never shown again.'
  if (field.fieldtype === 'Link' && !field.description) return `Links to ${field.options}.`
  return plainText(field.description)
}

// A heading and the first field under it read as one block, so the parent's divide-y rule is
// dropped between them. The rules that remain separate one field from the next, which is what
// they are for — a rule directly under a heading only fences it off from what it heads.
function hasHeading(group) {
  return Boolean(group.logo || group.toggle || group.label)
}
</script>

<template>
  <template v-for="group in groups" :key="group.label">
    <!-- A group naming a provider shows its plate, the same registry the payment and
         shipping rows read; a group without one keeps the plain heading. -->
    <!-- No rule above a group heading: the plate and the space already separate the groups,
         and the parent's divide-y would draw a second line right under the one before it. -->
    <div v-if="group.logo || group.toggle" class="flex items-center gap-2 pt-5 !border-t-0">
      <IntegrationLogo v-if="group.logo" :slug="group.logo" :label="group.label" size="sm" />
      <p class="text-sm text-ink-gray-5">{{ group.label }}</p>
      <!-- The switch belongs beside the name it switches, not in a row of its own under it. -->
      <div v-if="group.toggle" class="ml-auto flex items-center">
        <SettingsFieldControl
          :field="group.toggle"
          :model-value="values[group.toggle.fieldname]"
          :aria-label="group.toggle.label"
          @update:model-value="emit('update', group.toggle.fieldname, $event)"
          @change="emit('commit', group.toggle.fieldname, $event, group.toggle.label)"
        />
      </div>
    </div>
    <p v-else-if="group.label" class="pt-5 text-sm text-ink-gray-5 !border-t-0">{{ group.label }}</p>
    <SettingsRow
      v-for="(field, index) in groupFields(group)"
      :key="field.fieldname"
      :class="index === 0 && hasHeading(group) ? '!border-t-0' : undefined"
      :title="field.required ? `${field.label} *` : field.label"
      :description="hint(field)"
    >
      <SettingsFieldControl
        :field="field"
        :model-value="values[field.fieldname]"
        :link-options-path="linkOptionsPath"
        @update:model-value="emit('update', field.fieldname, $event)"
        @change="emit('commit', field.fieldname, $event, field.label)"
      />
    </SettingsRow>
  </template>
</template>
