import assert from 'node:assert/strict'
import { test } from 'node:test'
import { languagePrefix, toBootLanguages } from '../../src/data/languageList.js'

const language = (code, published, direction = 'ltr') => ({ code, name: code, endonym: code, direction, published })

test('the default language lives at the root and the others under their code', () => {
  assert.equal(languagePrefix('ar', 'ar'), '/')
  assert.equal(languagePrefix('pt-BR', 'en'), '/pt-br/')
})

test('the boot list puts the default first, then published, then hidden languages', () => {
  const screen = {
    default_language: 'ar',
    languages: [language('fr', false), language('en', true), language('ar', true, 'rtl'), language('de', true)],
  }

  assert.deepEqual(
    toBootLanguages(screen).map(({ code }) => code),
    ['ar', 'en', 'de', 'fr'],
  )
  assert.deepEqual(toBootLanguages(screen)[0], { code: 'ar', name: 'ar', endonym: 'ar', direction: 'rtl' })
})
