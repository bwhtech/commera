import { createApp } from 'vue'
import { FrappeUI, useColorScheme } from 'frappe-ui'
import { router } from './router'
import { applyDocumentDirection, isSignedIn } from './data/boot'
import { installTelemetry } from './telemetry'
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
app.directive('scroll-fade', scrollFade)
// docs/telemetry.md: the merchant is the product user, so nothing goes out without a session.
if (isSignedIn) installTelemetry(app, router)
app.mount('#app')
