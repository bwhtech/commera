import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  STEP_INDEX,
  abbreviate,
  canFinish,
  clampStep,
  missingField,
  resumeStep,
  stepDurationBucket,
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

test('a reload resumes at the saved step, unless the store setup never started', () => {
  assert.equal(resumeStep(STEP_INDEX.theme, 'running'), STEP_INDEX.theme)
  assert.equal(resumeStep(STEP_INDEX.theme, 'idle'), STEP_INDEX.store)
  assert.equal(resumeStep(STEP_INDEX.store, 'idle'), STEP_INDEX.store)
  assert.equal(resumeStep(99, 'done'), STEP_INDEX.done)
  assert.equal(clampStep(Number.NaN), 0)
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

test('stepDurationBucket buckets the time on a step at the docs/telemetry.md edges', () => {
  assert.equal(stepDurationBucket(0), 'lt_10s')
  assert.equal(stepDurationBucket(9_999), 'lt_10s')
  assert.equal(stepDurationBucket(10_000), '10_30s')
  assert.equal(stepDurationBucket(29_999), '10_30s')
  assert.equal(stepDurationBucket(30_000), '30_120s')
  assert.equal(stepDurationBucket(119_999), '30_120s')
  assert.equal(stepDurationBucket(120_000), 'gt_120s')
  assert.equal(stepDurationBucket(3_600_000), 'gt_120s')
})
