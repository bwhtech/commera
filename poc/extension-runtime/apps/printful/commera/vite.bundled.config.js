// Experiment: the same app, but with its own copy of frappe-ui bundled in.
import { defineConfig } from 'vite'
import { fileURLToPath } from 'node:url'
import frappeui from 'frappe-ui/vite'
import commera from '@commera/extension-kit/vite'

export default defineConfig({
  define: { 'process.env.NODE_ENV': JSON.stringify('production') },
  plugins: [
    frappeui({ frappeProxy: false, jinjaBootData: false, buildConfig: false }),
    ...commera({ root: fileURLToPath(new URL('..', import.meta.url)), bundleFrappeUI: true }),
  ],
})
