<script setup>
/**
 * An installed app's own Settings tab. Commera draws the heading; an app that only names its settings
 * Single gets the same self-saving rows as Advanced, and one with a template fills the body itself.
 */
import { ref, watch } from 'vue'
import { Button, SettingsBody } from 'frappe-ui'
import SettingsPanelHeader from './SettingsPanelHeader.vue'
import SettingsFieldRows from './SettingsFieldRows.vue'
import SettingsSkeleton from './SettingsSkeleton.vue'
import EmptyState from '../EmptyState.vue'
import ExtensionHost from '../ExtensionHost.vue'
import { useAdminAction, useAdminRead } from '../../data/api'
import { appTitle } from '../../ia/extensions'
import { useSettingsAutosave } from '../../data/useSettingsAutosave'

const props = defineProps({
  entry: { type: Object, required: true },
  active: { type: Boolean, default: false },
})

const appSettings = useAdminRead('extensions.get_app_settings', {
  params: { app: props.entry.app },
  immediate: false,
})
const saveSetting = useAdminAction('extensions.save_app_setting')

// useSettingsAutosave submits { [fieldname]: value }; this endpoint takes one field by name.
const save = {
  submit: async (fields) => {
    const [[fieldname, value]] = Object.entries(fields)
    return { [fieldname]: await saveSetting.submit({ app: props.entry.app, fieldname, value }) }
  },
  get error() {
    return saveSetting.error
  },
}

const { values, adopt, set, commit } = useSettingsAutosave(save)

watch(
  () => appSettings.data,
  (data) => data && adopt(data.values),
  { immediate: true },
)

// An app's module loads the first time its tab is shown, then stays, like the dialog's other panels.
const shown = ref(false)

watch(
  () => props.active,
  (isActive) => {
    if (!isActive) return
    shown.value = true
    if (props.entry.doctype && !appSettings.isFinished) appSettings.reload()
  },
  { immediate: true },
)

// A controller can rewrite a value on save and a secret is never echoed back, so the tab is re-read.
async function commitField(fieldname, value, label) {
  await commit(fieldname, value, label, () => appSettings.reload())
}
</script>

<template>
  <SettingsPanelHeader :title="entry.label" :description="`Added by ${appTitle(entry.app)}.`" />

  <SettingsBody v-scroll-fade>
    <template v-if="entry.doctype">
      <EmptyState
        v-if="appSettings.error"
        compact
        icon="lucide-triangle-alert"
        title="These settings could not be loaded"
        :description="`${appTitle(entry.app)} may still be set up. This tab just cannot say.`"
      >
        <Button label="Try again" variant="subtle" theme="gray" @click="appSettings.reload()" />
      </EmptyState>
      <SettingsSkeleton v-else-if="!appSettings.data" :rows="3" />
      <div v-else class="divide-y divide-outline-gray-1">
        <SettingsFieldRows :groups="appSettings.data.groups" :values="values" @update="set" @commit="commitField" />
      </div>
    </template>

    <ExtensionHost v-else-if="shown" :entry="entry" />
  </SettingsBody>
</template>
