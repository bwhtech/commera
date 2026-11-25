import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'
import { compileScript, parse } from '@vue/compiler-sfc'
import { createSSRApp } from 'vue'
import { renderToString } from 'vue/server-renderer'

const source = await readFile(new URL('../../src/components/settings/SettingsFieldRows.vue', import.meta.url), 'utf8')
const { descriptor } = parse(source)
const compiled = compileScript(descriptor, { id: 'settings-field-rows-test', inlineTemplate: true })
const moduleUrl = (code) => `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
const vueUrl = import.meta.resolve('vue')
const stubUrl = moduleUrl(
  `export default { props: ['title', 'description'], template: '<div>{{ title }}|{{ description }}<slot /></div>' }`,
)
let code = compiled.content.replaceAll('from "vue"', `from '${vueUrl}'`)
code = code.replace(/import .* from '([^']+)'/g, (line, path) => {
  if (path.endsWith('.vue')) return line.replace(path, stubUrl)
  if (path === 'frappe-ui') return `import SettingsRow from '${stubUrl}'`
  if (path.endsWith('/translation')) return 'const __ = (message) => message'
  return line
})

test('a link field without a description shows no made-up hint', async () => {
  const { default: SettingsFieldRows } = await import(moduleUrl(code))
  const groups = [{ label: 'Price List', fields: [{ fieldname: 'price_list', label: 'Default Price List', fieldtype: 'Link', options: 'Price List' }] }]
  const html = await renderToString(createSSRApp(SettingsFieldRows, { groups, values: {} }))

  assert.match(html, /Default Price List/)
  assert.doesNotMatch(html, /Links to/)
})

test('a secret shows a hint only once it is saved', async () => {
  const { default: SettingsFieldRows } = await import(moduleUrl(code))
  const secret = { fieldname: 'key_secret', label: 'Key Secret', fieldtype: 'Password', is_secret: true }
  const render = (isSet) =>
    renderToString(
      createSSRApp(SettingsFieldRows, { groups: [{ label: 'API Keys', fields: [{ ...secret, is_set: isSet }] }], values: {} }),
    )

  assert.doesNotMatch(await render(false), /Stored/)
  assert.match(await render(true), /Stored\. Leave blank to keep it\./)
})
