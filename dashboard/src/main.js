import { createApp } from 'vue'
import { FrappeUI, useColorScheme } from 'frappe-ui'
import { router } from './router'
import { applyDocumentDirection } from './data/boot'
import { translation } from './data/translation'
import { scrollFade } from './utils/scrollFade'
import './style.css'
import App from './App.vue'

// Restores the saved light/dark preference before the first paint. Settings →
// Appearance writes it; this reads it back.
useColorScheme()

// The session's language/direction rides the boot payload (see data/boot.js)
// rather than being guessed from the browser, same as the rest of the shell.
applyDocumentDirection()

const app = createApp(App)
app.use(router)
app.use(FrappeUI)
app.use(translation)
app.directive('scroll-fade', scrollFade)
app.mount('#app')
