<script setup>
/**
 * The analytics services this store reports to.
 *
 * Each is the same shape — a switch, public ids, and one credential the server keeps — so they are
 * described as docfields and rendered by the same row renderer the provider screens use, rather
 * than hand-built a third time.
 *
 * Every control saves its own field the moment it settles, so there is no Save button.
 */
import { computed, watch } from 'vue'
import { SettingsBody, SettingsHeader } from 'frappe-ui'
import EmptyState from '../EmptyState.vue'
import SettingsFieldRows from './SettingsFieldRows.vue'
import SettingsSkeleton from './SettingsSkeleton.vue'
import { useAdminAction, useAdminRead } from '../../data/api'
import { useSettingsAutosave } from '../../data/useSettingsAutosave'

const props = defineProps({
  active: { type: Boolean, default: false },
})

const PLAIN_FIELDS = [
  'enable_first_party',
  'enable_ga4',
  'ga4_measurement_id',
  'ga4_property_id',
  'enable_facebook',
  'fb_pixel_id',
]

const SECRET_FIELDS = ['ga4_service_account_json', 'fb_access_token']

const analytics = useAdminRead('analytics.get_analytics_settings', { immediate: false })
const save = useAdminAction('analytics.save_analytics_settings')

const { values, adopt, set, commit } = useSettingsAutosave(save)

// A secret is never returned, so it starts blank on every load and blank means "keep it".
function blankSecrets() {
  return Object.fromEntries(SECRET_FIELDS.map((fieldname) => [fieldname, '']))
}

function plainFields(data) {
  return Object.fromEntries(PLAIN_FIELDS.map((fieldname) => [fieldname, data[fieldname]]))
}

function adoptSettings(data) {
  adopt({ ...plainFields(data), ...blankSecrets() })
}

watch(
  () => analytics.data,
  (data) => data && adoptSettings(data),
  { immediate: true },
)

watch(
  () => props.active,
  (isActive) => isActive && !analytics.isFinished && analytics.reload(),
  { immediate: true },
)

const groups = computed(() => [
  {
    label: 'This store',
    fields: [
      {
        fieldname: 'enable_first_party',
        label: 'Track visits in Commera',
        fieldtype: 'Check',
        description: 'Powers the Storefront report. Nothing leaves this site.',
      },
    ],
  },
  {
    label: 'Google Analytics 4',
    logo: 'ga4',
    toggle: { fieldname: 'enable_ga4', label: 'Send events to GA4', fieldtype: 'Check' },
    fields: [
      {
        fieldname: 'ga4_measurement_id',
        label: 'Measurement ID',
        fieldtype: 'Data',
        description: 'Starts with G-. In GA4 it is under Admin, Data streams.',
      },
      {
        fieldname: 'ga4_property_id',
        label: 'Property ID',
        fieldtype: 'Data',
        description: 'The numeric property, used to read reports back out of GA4.',
      },
      {
        fieldname: 'ga4_service_account_json',
        label: 'Service account JSON',
        fieldtype: 'Data',
        is_secret: true,
        is_set: Boolean(analytics.data?.ga4_service_account_json_is_set),
      },
    ],
  },
  {
    label: 'Meta',
    logo: 'meta',
    toggle: { fieldname: 'enable_facebook', label: 'Send events to Meta', fieldtype: 'Check' },
    fields: [
      { fieldname: 'fb_pixel_id', label: 'Pixel ID', fieldtype: 'Data' },
      {
        fieldname: 'fb_access_token',
        label: 'Access token',
        fieldtype: 'Data',
        is_secret: true,
        is_set: Boolean(analytics.data?.fb_access_token_is_set),
      },
    ],
  },
])

// A blank secret means "keep the stored one": it matches the blank this panel adopted, so it is
// never submitted. Whether a secret is stored is read off the loaded settings rather than off the
// save's answer, so a freshly stored credential only stops reading as missing once they are re-read.
async function commitField(fieldname, value, label) {
  const isSecret = SECRET_FIELDS.includes(fieldname)
  await commit(fieldname, value, label, (saved) =>
    isSecret ? analytics.reload() : adopt(plainFields(saved)),
  )
}
</script>

<template>
  <SettingsHeader
    title="Analytics"
    description="The analytics and marketing services this store reports to."
  />

  <SettingsBody>
    <!-- The refusal itself is already toasted by useAdminRead. This says why the panel is
         empty, so an empty screen never reads as "nothing is connected". -->
    <EmptyState
      v-if="analytics.error"
      compact
      icon="lucide-lock"
      title="Hidden from your role"
      description="These credentials are only visible to a System Manager."
    />

    <SettingsSkeleton v-else-if="!analytics.data" :rows="6" />

    <div v-else class="divide-y divide-outline-gray-1">
      <SettingsFieldRows :groups="groups" :values="values" @update="set" @commit="commitField" />
    </div>
  </SettingsBody>
</template>
