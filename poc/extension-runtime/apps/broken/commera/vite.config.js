import { defineConfig } from 'vite'
import { fileURLToPath } from 'node:url'
import commera from '@commera/extension-kit/vite'

// In a bench the kit reads apps/commera's build; here the sibling host folder.
export default defineConfig({
  plugins: commera({
    root: fileURLToPath(new URL('..', import.meta.url)),
    hostClasses: fileURLToPath(new URL('../../../host/dist/classes.json', import.meta.url)),
    hostExports: fileURLToPath(new URL('../../../host/dist/shared-exports.json', import.meta.url)),
  }),
})
