import { computed, ref } from 'vue'
import { toast } from 'frappe-ui'
import { useAdminAction, wasAborted } from './api'
import { errorMessage } from './errors'
import { errorField } from './marketUrls'
import { marketStore } from './markets'
import { __ } from './translation'
import { useSettingsAutosave } from './useSettingsAutosave'

export const NEW_MARKET = 'new'

const DRAFT_FIELDS = [
  'market_name',
  'handle',
  'countries',
  'languages',
  'default_language',
  'sale_price_list',
  'compare_at_price_list',
]

// An existing market saves each field as it settles; a new one is a draft until created. A refusal
// that names a field lands in `errors`, so the editor shows it on that field instead of a toast.
export function useMarketForm(handle) {
  const isNew = handle === NEW_MARKET
  const errors = ref({})
  const hasError = computed(() => Object.keys(errors.value).length > 0)

  // Quiet: a refusal that names a field is shown on the field; the rest are toasted in report().
  const updateAction = useAdminAction('markets.update_market', { quiet: true })
  const createAction = useAdminAction('markets.create_market', { quiet: true })
  const { values, adopt, set, commit } = useSettingsAutosave(reportingErrors(updateAction), { params: { handle } })
  adopt(isNew ? blankMarket() : marketStore.find(handle))

  function reportingErrors(action) {
    return {
      async submit(params) {
        try {
          const saved = await action.submit(params)
          errors.value = {}
          return saved
        } catch (error) {
          report(error)
          throw error
        }
      },
    }
  }

  function report(error) {
    if (wasAborted(error)) return
    const field = errorField(error, marketStore.choices.value?.error_fields)
    if (field) errors.value = { [field]: errorMessage(error) }
    else toast.error(errorMessage(error))
  }

  function change(fieldname, value, label) {
    if (isNew) {
      set(fieldname, value)
      errors.value = {}
      return
    }
    return commit(fieldname, value, label, (saved) => {
      adopt(saved)
      marketStore.upsert(saved)
    })
  }

  // The server hands a dropped default to the next language; a draft does the same here.
  function setLanguages(languages) {
    if (isNew && !languages.includes(values.value.default_language)) {
      set('default_language', languages[0] ?? '')
    }
    change('languages', languages, __('Languages'))
  }

  const canCreate = computed(() => {
    const draft = values.value
    return Boolean(
      draft.market_name?.trim() && draft.countries.length && draft.languages.length && draft.sale_price_list,
    )
  })

  async function create() {
    const params = Object.fromEntries(DRAFT_FIELDS.map((fieldname) => [fieldname, values.value[fieldname]]))
    if (marketStore.choices.value?.tax_templates) params.tax_template = values.value.tax_template
    try {
      const saved = await createAction.submit(params)
      marketStore.upsert(saved)
      toast.success(__('{0} created', [saved.market_name]))
      return saved.handle
    } catch (error) {
      report(error)
      return null
    }
  }

  return {
    isNew,
    values,
    errors,
    hasError,
    canCreate,
    creating: computed(() => createAction.loading),
    set,
    change,
    setLanguages,
    create,
  }
}

function blankMarket() {
  return {
    is_primary: false,
    enabled: 1,
    market_name: '',
    handle: '',
    countries: [],
    languages: [],
    default_language: '',
    sale_price_list: '',
    compare_at_price_list: '',
    tax_template: '',
  }
}
