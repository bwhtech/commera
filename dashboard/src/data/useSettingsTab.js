import { watch } from 'vue'
import { useAdminAction, useAdminRead } from './api'
import { useSettingsAutosave } from './useSettingsAutosave'

/**
 * A settings tab that reads and autosaves one fixed group of Commera Settings fields. The server
 * names each group by `tab`, and refuses a write to any field outside it.
 */
export function useSettingsTab(tab, isActive) {
  const settings = useAdminRead('settings.get_tab_settings', { immediate: false, params: { tab } })
  const save = useAdminAction('settings.save_tab_settings')
  const autosave = useSettingsAutosave(save, { params: { tab } })

  watch(
    () => settings.data,
    (data) => data && autosave.adopt(data),
    { immediate: true },
  )

  // Opening the tab should fetch; switching away and back should not.
  watch(
    isActive,
    (active) => {
      if (active && !settings.isFinished) settings.reload()
    },
    { immediate: true },
  )

  return { settings, save, ...autosave }
}
