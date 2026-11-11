import { createLanguageSettingsStore } from './languageSettingsStore.js'
import { createAdminCaller } from './adminCaller'
import { wasAborted } from './api'
import { setStorefrontLanguages } from './boot'
import { toBootLanguages } from './languageList'

export { languagePrefix } from './languageList'

export const storefrontLanguageSettings = createLanguageSettingsStore({
  ...createAdminCaller('storefront_languages.'),
  wasAborted,
  onAdopt: (data) => setStorefrontLanguages(toBootLanguages(data)),
})
