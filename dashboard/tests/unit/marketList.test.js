import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'
import { compileScript, parse } from '@vue/compiler-sfc'
import { createSSRApp, ref } from 'vue'
import { renderToString } from 'vue/server-renderer'

const source = await readFile(new URL('../../src/components/settings/markets/MarketList.vue', import.meta.url), 'utf8')
const { descriptor } = parse(source)
const compiled = compileScript(descriptor, { id: 'market-list-test', inlineTemplate: true })
const moduleUrl = (code) => `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
const vueUrl = import.meta.resolve('vue')
const stubUrl = moduleUrl(`export default { props: ['title', 'label'], template: '<div>{{ title }}{{ label }}<slot /></div>' }`)
let code = compiled.content.replaceAll('from "vue"', `from '${vueUrl}'`)
code = code.replace(/import .* from '([^']+)'/g, (line, path) => {
  if (path.endsWith('.vue')) return line.replace(path, stubUrl)
  if (path === 'frappe-ui') return `import Stub from '${stubUrl}'; const Badge = Stub, Button = Stub, SettingsBody = Stub, Switch = Stub`
  if (path.endsWith('/markets')) return 'const marketStore = globalThis.marketListTest'
  if (path.endsWith('/marketUrls')) return 'const urlSummary = () => ""'
  if (path.endsWith('/useMarketForm')) return 'const NEW_MARKET = null'
  if (path.endsWith('/translation')) return 'const __ = (message) => message'
  return line
})

test('a choices failure after markets load shows Retry and recovers after a reload', async () => {
  const store = {
    markets: ref([]),
    choices: ref(null),
    loadError: ref(new Error('Choices failed')),
    load() { this.choices.value = {}; this.loadError.value = null },
  }
  globalThis.marketListTest = store
  const { default: MarketList } = await import(moduleUrl(code))
  const failed = await renderToString(createSSRApp(MarketList))
  assert.match(failed, /These could not be loaded/)
  assert.match(failed, /Try again/)
  store.markets.value = null
  store.choices.value = {}
  store.loadError.value = new Error('Markets failed')
  const listFailed = await renderToString(createSSRApp(MarketList))
  assert.match(listFailed, /Try again/)
  store.markets.value = []
  store.load()
  const recovered = await renderToString(createSSRApp(MarketList))
  assert.doesNotMatch(recovered, /Try again/)
  assert.match(recovered, /<ul/)
})
