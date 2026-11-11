import { useAdminAction, useAdminRead } from './api'

// Fetched when the picker opens rather than at boot: most sessions never change language.
export function useLanguages() {
  return useAdminRead('language.get_languages', {
    immediate: false,
    transform: ({ current, languages }) => ({ current, options: languages.map(toLanguageOption) }),
  })
}

export function useSetLanguage() {
  return useAdminAction('language.set_language')
}

// The endonym leads, so an admin who cannot read the current language still finds their own.
function toLanguageOption(language) {
  const description = language.endonym === language.name ? undefined : language.name
  return { label: language.endonym, value: language.code, description }
}
