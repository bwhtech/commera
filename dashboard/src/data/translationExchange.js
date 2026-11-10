import { storefrontLanguages } from './boot.js'

// v1, not the v2 door in api.js: the browser downloads this, and only v1 answers with the file itself.
export function exportTranslationsUrl(language) {
  const params = new URLSearchParams({ language })
  return `/api/method/commera.api.admin.translations.export_translations?${params}`
}

// The default language comes first and is the source the others translate, so it is left out.
export function translatableLanguages(languages = storefrontLanguages) {
  return languages.slice(1)
}
