import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'
import { compileScript, parse } from '@vue/compiler-sfc'
import { createSSRApp, ref } from 'vue'
import { renderToString } from 'vue/server-renderer'

const source = await readFile(new URL('../../src/pages/storefront/Themes.vue', import.meta.url), 'utf8')
const { descriptor } = parse(source)
const compiled = compileScript(descriptor, { id: 'theme-library-test', inlineTemplate: true })
const moduleUrl = (code) => `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
const vueUrl = import.meta.resolve('vue')
const stubUrl = moduleUrl(
  `export default { props: ['theme', 'title'], template: '<div :data-theme="theme && theme.name">{{ title }}<slot /></div>' }`,
)
let code = compiled.content.replaceAll('from "vue"', `from '${vueUrl}'`).replaceAll("from 'vue'", `from '${vueUrl}'`)
code = code.replace(/import .* from '([^']+)'/g, (line, path) => {
  if (path.endsWith('.vue')) return line.replace(path, stubUrl)
  if (path === 'frappe-ui') return `import Stub from '${stubUrl}'; const Button = Stub, Skeleton = Stub, dialog = {}, toast = {}`
  if (path.endsWith('/theme')) return 'const useTheme = () => globalThis.themeLibraryTest'
  if (path.endsWith('/storePreview')) return 'const captureMissingThumbnails = () => {}'
  if (path.endsWith('/errors')) return 'const errorMessage = String'
  if (path.endsWith('/translation')) return 'const __ = (message) => message'
  return line
})

test('the theme library leaves out the base theme no store can switch to', async () => {
  globalThis.themeLibraryTest = {
    themes: ref([
      { name: 'Summer Theme', live: true },
      { name: 'Commera Starter', live: false },
      { name: 'Shop Base Theme', live: false, is_base: true },
    ]),
    loadError: ref(null),
    loading: ref(false),
    builderInstalled: ref(false),
    load: async () => {},
    activate: async () => {},
  }
  const { default: Themes } = await import(moduleUrl(code))
  const html = await renderToString(createSSRApp(Themes))

  assert.match(html, /data-theme="Commera Starter"/)
  assert.doesNotMatch(html, /data-theme="Shop Base Theme"/)
})
