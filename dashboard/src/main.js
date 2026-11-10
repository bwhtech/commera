import { loadTranslations } from './data/translation'

// Modules translate their labels as they load, so the app is imported only once the strings are in.
loadTranslations().then(() => import('./app.js'))
