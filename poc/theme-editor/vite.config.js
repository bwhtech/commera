import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import frappeui from 'frappe-ui/vite'
import { fileURLToPath } from 'node:url'

const page = (file) => fileURLToPath(new URL(file, import.meta.url))

// Two pages: the dashboard editor (index.html) and the storefront preview it
// embeds in an iframe (preview.html). In Commera the preview is a Jinja route
// rendering the draft layout; here it is plain JS mimicking those templates.
export default defineConfig({
  plugins: [frappeui({ frappeProxy: false, jinjaBootData: false, buildConfig: false }), vue()],
  build: {
    target: 'es2022',
    rollupOptions: { input: { index: page('./index.html'), preview: page('./preview.html') } },
  },
})
