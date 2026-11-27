// The product import flow: shared state for one run of it. Every step reads and writes the real
// commera.api.admin.imports endpoints, and photos are matched to a product color by file name
// (imports.match_import_images).
import { computed, reactive, ref, watch } from 'vue'
import { errorMessage } from './errors'
import { trySubmit, useAdminAction, useAdminRead } from './api'
import { canMove, createdProducts, isBusy, nextPhase } from './importPhase'
import { isSameMapping, remapColumn, suggestionParams } from './importMapping'
import { stepIndex, stepsFor } from './importSteps'

export const steps = computed(() => stepsFor(imp.source, imp.hasSourceChoice === true))

// `open` is deliberately not part of this shape: resetImport() runs from openImport() while the
// dialog is being shown, and clearing `open` there would tear the dialog down as it opens.
function blankImport() {
  return {
    step: 0,
    source: 'csv',
    // null until the dialog has asked whether ERPNext has items to bring in; the Source step is
    // only a step when there is a second source to pick.
    hasSourceChoice: null,
    imagesMode: 'bulk',
    // See importPhase.js: the one value that says what the flow is waiting on.
    phase: 'idle',
    file: null,
    fileUrl: null,
    parsed: false,
    fileError: '',
    // Photos: every file the browser has uploaded, the merchant's manual pick per file, what the
    // server matched back, and the {group key: [file_url]} map handed to run_import.
    imageFiles: [],
    imageChoices: {},
    imageMatch: null,
    imageAssignments: {},
    reviewFilter: 'all',
    // `mapping` is what the Map step shows; `checkedMapping` is the one the rows and counts were
    // computed from. Only when the two agree may the flow leave the Map step.
    mapping: {},
    checkedMapping: null,
    checkedCollection: '',
    checkError: '',
    suggestedMapping: {},
    confidence: {},
    missing: [],
    defaultCollection: '',
    headers: [],
    preview: [],
    samples: {},
    rows: [],
    counts: { total: 0, ready: 0, warnings: 0, errors: 0, products: 0, variants: 0 },
    created: [],
    published: null,
    runRowErrors: [],
    runImageErrors: [],
    imagesAttached: 0,
    erpnext: {
      importableCount: 0,
      items: [],
      skipped: [],
      total: 0,
      search: '',
      page: 1,
      pageSize: 50,
      tab: 'items',
      allItemCodes: [],
      selected: [],
      selectionReady: false,
      jobId: null,
      log: null,
      status: null,
      poll: 'off',
      error: '',
      published: null,
    },
  }
}

export const imp = reactive({ open: false, ...blankImport() })

// Bumped when the dialog closes on a run that created products, so lists read before it reload.
export const importsLanded = ref(0)
watch(
  () => imp.open,
  (open) => {
    if (!open && createdProducts(imp)) importsLanded.value += 1
  },
)

// Bumped on every reset. A request started before a reset — a spreadsheet still uploading when the
// dialog was closed and reopened, a photo upload loop — holds the old number and must not write its
// answer into the fresh flow.
let session = 0

export const importBusy = computed(() => isBusy(imp.phase))
export const canChangeStep = computed(() => canMove(imp.phase))

// Every async step starts here and gets a ticket back, or null when something else is in flight
// (or the import already landed), which makes a second click a no-op rather than a second request.
export function beginPhase(phase) {
  const next = nextPhase(imp.phase, phase)
  if (!next) return null
  imp.phase = next
  return session
}

// True when the ticket still belongs to this flow, so its answer may be written.
export const isCurrentImport = (ticket) => ticket === session

// Ends the phase a ticket started; a ticket from before a reset changes nothing.
export function endPhase(ticket, phase = 'idle') {
  if (!isCurrentImport(ticket)) return false
  imp.phase = phase
  return true
}

export function resetImport() {
  session += 1
  Object.assign(imp, blankImport())
}

// Removing the spreadsheet forgets everything read from it — the mapping, the counts and the photo
// matches are all keyed to its rows, and run_import would otherwise get the old file's photo map.
// The photos already uploaded are kept: they are the merchant's files, and the next match re-places them.
export function clearImportFile() {
  const { step, source, hasSourceChoice, imagesMode, imageFiles, erpnext } = imp
  resetImport()
  Object.assign(imp, { step, source, hasSourceChoice, imagesMode, imageFiles, erpnext })
}

export function goToStep(key) {
  imp.step = stepIndex(imp.source, key, imp.hasSourceChoice === true)
}

export function openImport(source) {
  // A run still in flight is shown again rather than reset: its write is landing either way, and
  // the merchant should see what it did.
  const awaitingPublish = imp.source === 'erpnext' && imp.phase === 'done' && !imp.erpnext.published
  if (imp.phase !== 'running' && !awaitingPublish && (imp.phase === 'done' || imp.file)) resetImport()
  if (typeof source === 'string' && imp.step === 0 && imp.phase === 'idle') {
    imp.source = source
    imp.hasSourceChoice = true
    imp.step = Math.max(0, stepIndex(source, 'pick'))
  }
  imp.open = true
}

export function closeImport() {
  imp.open = false
}

// One action, shared by the Upload preview and every mapping change: a dry run of what run_import
// would write (see RunStep).
export const validateImportAction = useAdminAction('imports.validate_import')

// The Map step's answer, as validate_import, match_import_images and run_import all take it. The
// collection for every row only applies while no column is matched to Collection.
export function importParams(mapping = imp.mapping) {
  const params = { file_url: imp.fileUrl, column_mapping: { ...mapping } }
  if (!Object.values(mapping).includes('collection') && imp.defaultCollection) params.default_collection = imp.defaultCollection
  return params
}

export function applyValidation(data, defaultCollection = imp.defaultCollection) {
  imp.headers = data.headers
  imp.mapping = { ...data.mapping }
  imp.checkedMapping = { ...data.mapping }
  imp.checkedCollection = defaultCollection
  imp.checkError = ''
  imp.suggestedMapping = data.suggested_mapping
  imp.confidence = data.confidence
  imp.missing = data.missing
  imp.preview = data.preview
  imp.samples = data.samples
  imp.rows = data.rows
  imp.counts = data.counts
  // New rows mean new buckets: a filter picked on the old ones may now hide every row.
  imp.reviewFilter = 'all'
  // Photo groups are product + color, read through the mapping, so a new mapping means the old
  // match may name groups that no longer exist. Images re-matches whenever this is empty.
  imp.imageMatch = null
  imp.imageAssignments = {}
}

export const isMappingChecked = computed(
  () =>
    imp.checkedMapping !== null &&
    isSameMapping(imp.mapping, imp.checkedMapping) &&
    (Object.values(imp.mapping).includes('collection') || imp.defaultCollection === imp.checkedCollection),
)

// Checks the mapping on screen. A change made while a check is in flight is kept, and checked as
// soon as that answer lands, so the rows Review shows are always the current mapping's.
export async function checkMapping({ useSuggestions = false } = {}) {
  const ticket = beginPhase('checking')
  if (ticket === null) return
  const sentMapping = { ...imp.mapping }
  const sentCollection = imp.defaultCollection
  const params = useSuggestions ? suggestionParams(imp.fileUrl, sentCollection) : importParams(sentMapping)
  const checked = await trySubmit(validateImportAction, params)
  if (!endPhase(ticket)) return
  if (!checked) {
    imp.checkError = errorMessage(validateImportAction.error)
    return
  }
  const isStale = !useSuggestions && (!isSameMapping(sentMapping, imp.mapping) || sentCollection !== imp.defaultCollection)
  if (isStale) return checkMapping()
  applyValidation(validateImportAction.data, sentCollection)
  await fillDefaultCollection()
}

export function setColumnField(header, field) {
  imp.mapping = remapColumn(imp.mapping, header, field)
  if (imp.phase !== 'checking') checkMapping()
}

export function setDefaultCollection(collection) {
  imp.defaultCollection = collection
  if (imp.phase !== 'checking') checkMapping()
}

const defaultCollectionRequest = useAdminRead('catalog.get_default_collection', { immediate: false, quiet: true })

// A file with no collection column starts on the collection the Add product dialog starts on,
// until the merchant picks another.
export async function fillDefaultCollection() {
  if (!imp.missing.includes('collection') || imp.defaultCollection) return
  const collection = await defaultCollectionRequest.fetch()
  if (collection && !imp.defaultCollection) setDefaultCollection(collection)
}

export const publishImportAction = useAdminAction('imports.publish_imported_products')

export async function publishImported() {
  if (imp.published || publishImportAction.loading) return
  const itemTemplates = imp.created.map((product) => product.item_template)
  if (await trySubmit(publishImportAction, { item_templates: itemTemplates })) imp.published = publishImportAction.data
}
