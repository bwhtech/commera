import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  SETUP_STAGES,
  STEP_INDEX,
  abbreviate,
  canFinish,
  clampStep,
  missingField,
  resumeStep,
  setupBuildLevel,
  setupPollDelay,
  storePicks,
  toOptions,
} from '../../src/ia/onboardingSteps.js'

const filled = { fullName: 'Aisha Khan', password: '', storeName: 'Indigo Loom', country: 'India', existingStore: false }

test('abbreviate matches frappe.utils.get_abbr with a five-letter cap', () => {
  assert.equal(abbreviate('Indigo Loom'), 'IL')
  assert.equal(abbreviate('indigo'), 'I')
  assert.equal(abbreviate('  The  Very Long Store Name Here '), 'TVLSN')
  assert.equal(abbreviate(''), '')
})

test('missingField names the first empty required field of a step', () => {
  assert.equal(missingField('you', filled), '')
  assert.equal(missingField('you', { ...filled, fullName: '  ' }), 'fullName')
  assert.equal(missingField('you', filled, { needsPassword: true }), 'password')
  assert.equal(missingField('you', { ...filled, password: 'secret' }, { needsPassword: true }), '')
  assert.equal(missingField('store', { ...filled, storeName: '' }), 'storeName')
  assert.equal(missingField('store', { ...filled, storeCategory: '' }), '')
  assert.equal(missingField('store', filled), '')
  assert.equal(missingField('store', { ...filled, country: 'India' }), '')
  assert.equal(missingField('store', { ...filled, country: '' }), 'country')
  assert.equal(missingField('store', { ...filled, existingStore: true }), '')
  assert.equal(missingField('done', { ...filled, storeName: '' }), '')
})

const existingStore = {
  company: '',
  companies: [
    { name: 'Acme India', default_currency: 'INR' },
    { name: 'Acme US', default_currency: 'USD' },
  ],
  price_lists: [
    { name: 'Retail', currency: 'INR' },
    { name: 'Wholesale', currency: 'INR' },
    { name: 'US Retail', currency: 'USD' },
  ],
}

test('a store ERPNext already set up picks only where there is a real choice', () => {
  assert.deepEqual(storePicks(null, ''), { companies: [], priceLists: [] })
  assert.deepEqual(storePicks(existingStore, ''), { companies: ['Acme India', 'Acme US'], priceLists: [] })
  assert.deepEqual(storePicks(existingStore, 'Acme India').priceLists, ['Retail', 'Wholesale'])
  assert.deepEqual(storePicks(existingStore, 'Acme US').priceLists, [])
  assert.deepEqual(storePicks({ ...existingStore, company: 'Acme US' }, 'Acme US'), { companies: [], priceLists: [] })
})

test('the store step asks for a company or price list only when it shows that picker', () => {
  const draft = { ...filled, existingStore: true, company: '', priceList: '' }
  assert.equal(missingField('store', draft), '')
  assert.equal(missingField('store', draft, { picks: storePicks(existingStore, '') }), 'company')
  const india = { ...draft, company: 'Acme India' }
  assert.equal(missingField('store', india, { picks: storePicks(existingStore, 'Acme India') }), 'priceList')
  const picks = storePicks(existingStore, 'Acme India')
  assert.equal(missingField('store', { ...india, priceList: 'US Retail' }, { picks }), 'priceList')
  assert.equal(missingField('store', { ...india, priceList: 'Wholesale' }, { picks }), '')
})

test('a reload resumes at the saved step, unless the store setup never started', () => {
  assert.equal(resumeStep('store', 'idle'), STEP_INDEX.store)
  assert.equal(resumeStep('done', 'running'), STEP_INDEX.done)
  assert.equal(resumeStep('done', 'idle'), STEP_INDEX.store)
  assert.equal(resumeStep(null, 'idle'), 0)
  assert.equal(resumeStep('gone', 'done'), 0)
  assert.equal(clampStep(Number.NaN), 0)
})

test('a retired step resumes at the store, or at done once the setup finished', () => {
  for (const key of ['brand', 'theme', 'selling', 'products']) {
    for (const status of ['idle', 'running', 'failed']) assert.equal(resumeStep(key, status), STEP_INDEX.store)
    assert.equal(resumeStep(key, 'done'), STEP_INDEX.done)
  }
})

test('a step saved as an index by an older build resumes at a step that still exists', () => {
  assert.equal(resumeStep('0', 'idle'), STEP_INDEX.you)
  assert.equal(resumeStep('1', 'idle'), STEP_INDEX.store)
  for (const index of ['2', '3', '4', '5']) {
    assert.equal(resumeStep(index, 'running'), STEP_INDEX.store)
    assert.equal(resumeStep(index, 'done'), STEP_INDEX.done)
  }
  assert.equal(resumeStep('6', 'done'), STEP_INDEX.done)
  assert.equal(resumeStep('99', 'done'), 0)
})

test('the store preview builds one piece per stage the job reaches, and the products once done', () => {
  assert.equal(setupBuildLevel('running', ''), 0)
  assert.equal(setupBuildLevel('running', 'company'), 1)
  assert.equal(setupBuildLevel('running', 'storefront'), 2)
  assert.equal(setupBuildLevel('failed', 'payments'), 3)
  assert.equal(setupBuildLevel('done', ''), SETUP_STAGES.length + 1)
})

test('onboarding can finish only once the store setup is done', () => {
  assert.equal(canFinish('done'), true)
  for (const status of ['idle', 'running', 'failed']) assert.equal(canFinish(status), false)
})

test('toOptions turns plain strings into label/value pairs and keeps objects', () => {
  assert.deepEqual(toOptions(['INR']), [{ label: 'INR', value: 'INR' }])
  assert.deepEqual(toOptions([{ label: 'A', value: 1 }]), [{ label: 'A', value: 1 }])
  assert.deepEqual(toOptions(undefined), [])
})

test('setupPollDelay slows after a minute and stops after ten', () => {
  assert.equal(setupPollDelay(0), 2000)
  assert.equal(setupPollDelay(59000), 2000)
  assert.equal(setupPollDelay(61000), 10000)
  assert.equal(setupPollDelay(10 * 60000), 10000)
  assert.equal(setupPollDelay(10 * 60000 + 1), null)
})
