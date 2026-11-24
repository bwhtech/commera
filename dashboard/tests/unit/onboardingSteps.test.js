import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  STEP_INDEX,
  abbreviate,
  canFinish,
  clampStep,
  missingField,
  resumeStep,
  setupPollDelay,
  storePicks,
  toOptions,
} from '../../src/ia/onboardingSteps.js'

const filled = { fullName: 'Aisha Khan', password: '', storeName: 'Indigo Loom', storeCategory: 'Fashion' }

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
  assert.equal(missingField('store', { ...filled, storeCategory: '' }), 'storeCategory')
  assert.equal(missingField('brand', { ...filled, storeName: '' }), '')
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
  assert.equal(resumeStep('selling', 'running'), STEP_INDEX.selling)
  assert.equal(resumeStep('selling', 'idle'), STEP_INDEX.store)
  assert.equal(resumeStep('store', 'idle'), STEP_INDEX.store)
  assert.equal(resumeStep('done', 'done'), STEP_INDEX.done)
  assert.equal(resumeStep(null, 'idle'), 0)
  assert.equal(resumeStep('gone', 'done'), 0)
  assert.equal(clampStep(Number.NaN), 0)
})

test('a step saved as an index before the look step went resumes at the same step', () => {
  assert.equal(resumeStep('2', 'running'), STEP_INDEX.brand)
  assert.equal(resumeStep('3', 'running'), STEP_INDEX.selling)
  assert.equal(resumeStep('4', 'running'), STEP_INDEX.selling)
  assert.equal(resumeStep('5', 'done'), STEP_INDEX.products)
  assert.equal(resumeStep('6', 'done'), STEP_INDEX.done)
  assert.equal(resumeStep('99', 'done'), 0)
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
