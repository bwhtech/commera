<script setup>
/**
 * The long tail of store setup: every remaining Commera Settings field, grouped by the section it
 * sits under in Desk and rendered from that doctype's own meta. Add a field to the doctype and it
 * appears here; nothing about this screen names a field.
 *
 * Every control saves its own field the moment it settles, so there is no Save button.
 */
import { watch } from 'vue'
import { Alert, Button, SettingsBody, SettingsHeader, dialog, toast } from 'frappe-ui'
import SettingsFieldRows from './SettingsFieldRows.vue'
import SettingsSkeleton from './SettingsSkeleton.vue'
import { useAdminAction, useAdminRead } from '../../data/api'
import { useSettingsAutosave } from '../../data/useSettingsAutosave'

const props = defineProps({
  active: { type: Boolean, default: false },
})

const advanced = useAdminRead('settings.get_advanced_settings', { immediate: false })
const save = useAdminAction('settings.save_advanced_settings')
const installDemoData = useAdminAction('settings.install_demo_data')

const { values, adopt, set, commit } = useSettingsAutosave(save)

function adoptSettings(data) {
  for (const group of data.groups) {
    adopt(Object.fromEntries(group.fields.map((field) => [field.fieldname, field.value])))
  }
}

watch(
  () => advanced.data,
  (data) => data && adoptSettings(data),
  { immediate: true },
)

watch(
  () => props.active,
  (isActive) => isActive && !advanced.isFinished && advanced.reload(),
  { immediate: true },
)

// The server answers with the fields it wrote, not with the screen, and a controller can rewrite
// a value on save — so the whole tab is re-read rather than assumed.
async function commitField(fieldname, value, label) {
  await commit(fieldname, value, label, () => advanced.reload())
}

// The seeder rewrites the homepage, the footer, the store currency and the payment accounts,
// so the confirmation names those rather than only the catalogue it also creates.
function confirmInstallDemoData() {
  dialog.confirm({
    title: 'Replace this store with demo data?',
    message:
      'It seeds a full demo catalogue, and overwrites your homepage, footer, store currency and payment accounts. Run it on a store you have not set up yet.',
    theme: 'red',
    confirmLabel: 'Install demo data',
    onConfirm: async () => {
      await installDemoData.submit()
      // useAdminAction has already toasted a refusal; a second toast here would stack on it.
      if (installDemoData.error) return
      toast.success('Demo data queued', {
        description: 'It runs in the background and takes a few minutes.',
      })
    },
  })
}
</script>

<template>
  <SettingsHeader
    title="Advanced"
    description="Every remaining store setting, grouped as it appears in your books."
  />

  <SettingsBody>
    <SettingsSkeleton v-if="advanced.loading && !advanced.data" class="mt-2" :rows="6" />

    <template v-else-if="advanced.data">
      <Alert
        class="mt-4"
        theme="amber"
        title="These are setup values, not everyday settings"
        description="Changing one can break your storefront — edit only what you recognise."
      />

      <div class="mt-2 divide-y divide-outline-gray-1">
        <SettingsFieldRows
          :groups="advanced.data.groups"
          :values="values"
          link-options-path="settings.get_link_options"
          @update="set"
          @commit="commitField"
        />
      </div>

      <!-- Lists of rows rather than single values, so this says where they live instead of
           pretending it can edit them. -->
      <div v-if="advanced.data.child_tables.length" class="mt-8 border-t border-outline-gray-1 pt-6">
        <h3 class="text-base font-medium text-ink-gray-8">Managed in Desk</h3>
        <p class="mt-1 text-p-sm text-ink-gray-5">
          These are lists rather than single values, so they are still edited on the Commera
          Settings form.
        </p>
        <ul class="mt-3 divide-y divide-outline-gray-1 border-y border-outline-gray-1">
          <li
            v-for="table in advanced.data.child_tables"
            :key="table.label"
            class="flex items-center justify-between gap-4 py-2.5"
          >
            <span class="text-base text-ink-gray-8">{{ table.label }}</span>
            <span class="text-sm text-ink-gray-5">{{ table.options }}</span>
          </li>
        </ul>
      </div>

      <!-- Hidden once the store has traded for itself: seeding overwrites the setup those
           orders were placed against, so the safe answer is not to offer it at all. -->
      <div v-if="advanced.data.can_install_demo_data" class="mt-8 border-t border-outline-gray-1 pt-6">
        <h3 class="text-base font-medium text-ink-gray-8">Demo data</h3>
        <p class="mt-1 text-p-sm text-ink-gray-5">
          Fills an empty store with a demo catalogue, menu, footer and banners so you can see how
          the storefront looks before you add your own products.
        </p>
        <Button
          class="mt-3"
          variant="subtle"
          theme="red"
          label="Install demo data"
          :loading="installDemoData.loading"
          @click="confirmInstallDemoData"
        />
      </div>
    </template>
  </SettingsBody>
</template>
