import assert from 'node:assert/strict'
import { test } from 'node:test'
import { getTrialNotice } from '../../src/data/trialNotice.js'

const activeTrial = (fields) => ({ state: 'Active', ends_on: '2026-11-20', days_left: 10, deletes_on: null, ...fields })

test('no trial means no notice', () => {
  assert.equal(getTrialNotice(null), null)
  assert.equal(getTrialNotice(undefined), null)
})

test('a trial with time left is a quiet, dismissible gray notice', () => {
  const notice = getTrialNotice(activeTrial({ days_left: 10 }))
  assert.equal(notice.theme, 'gray')
  assert.equal(notice.title, 'Your trial ends in 10 days')
  assert.equal(notice.dismissible, true)
})

test('the last three days turn amber', () => {
  assert.equal(getTrialNotice(activeTrial({ days_left: 3 })).theme, 'amber')
  assert.equal(getTrialNotice(activeTrial({ days_left: 1 })).title, 'Your trial ends tomorrow')
  assert.equal(getTrialNotice(activeTrial({ days_left: 0 })).title, 'Your trial ends today')
  assert.equal(getTrialNotice(activeTrial({ days_left: -1 })).title, 'Your trial ends today')
})

test('a held trial asks to manage billing', () => {
  const notice = getTrialNotice(activeTrial({ held: true, days_left: 10 }))
  assert.equal(notice.theme, 'amber')
  assert.equal(notice.actionLabel, 'Manage billing')
  assert.equal(notice.dismissible, true)
})

test('an ended trial is red, cannot be dismissed, and names the deletion day', () => {
  const notice = getTrialNotice({ state: 'Ended', days_left: 0, deletes_on: '2026-12-01', held: true })
  assert.equal(notice.theme, 'red')
  assert.equal(notice.dismissible, false)
  assert.match(notice.description, /deleted on .*1/)
})

test('an ended trial without a deletion day still asks for a plan', () => {
  const notice = getTrialNotice({ state: 'Ended', days_left: 0, deletes_on: null })
  assert.equal(notice.description, 'Choose a plan to keep using your store.')
})
