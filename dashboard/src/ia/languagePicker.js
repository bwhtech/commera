import { ref } from 'vue'

// Both shells' account menus open the one dialog App.vue mounts.
export const languagePickerOpen = ref(false)

export function openLanguagePicker() {
  languagePickerOpen.value = true
}
