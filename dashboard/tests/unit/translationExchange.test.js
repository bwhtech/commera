import assert from 'node:assert/strict'
import { test } from 'node:test'
import { exportTranslationsUrl, translatableLanguages } from '../../src/data/translationExchange.js'

test('the export link names the admin method and the language', () => {
  assert.equal(
    exportTranslationsUrl('pt-BR'),
    '/api/method/commera.api.admin.translations.export_translations?language=pt-BR',
  )
})

test('every storefront language but the default can be translated', () => {
  const languages = [{ code: 'en' }, { code: 'ar' }, { code: 'fr' }]
  assert.deepEqual(translatableLanguages(languages).map(({ code }) => code), ['ar', 'fr'])
  assert.deepEqual(translatableLanguages([]), [])
})
