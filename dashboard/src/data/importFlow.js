// The product import flow: shared state for one run of it. Every step reads and writes the real
// commera.api.admin.imports endpoints — the spreadsheet is the only source that exists, and photos
// are matched to a product colour by file name (imports.match_import_images).
import { computed, reactive } from 'vue'
import { useAdminAction } from './api'
import { canMove, isBusy, nextPhase } from './importPhase'
import { __ } from './translation'

export const STEPS = [
  { key: 'source', label: __('Source'), icon: 'lucide-plug', hint: __('Where the products live today') },
  { key: 'upload', label: __('Upload'), icon: 'lucide-file-up', hint: __('Your spreadsheet') },
  { key: 'map', label: __('Match columns'), icon: 'lucide-arrow-left-right', hint: __('Your headings to ours') },
  { key: 'images', label: __('Images'), icon: 'lucide-image', hint: __('Photos for each product') },
  { key: 'review', label: __('Review'), icon: 'lucide-list-checks', hint: __('Check before saving') },
  { key: 'run', label: __('Import'), icon: 'lucide-rocket', hint: __('Create everything') },
]

// TARGET_FIELDS/REQUIRED mirror commera.api.admin.imports.FIELD_SYNONYMS/REQUIRED_FIELDS field
// for field — a mismatch here means a column that maps cleanly on the server shows the wrong
// label here, not a functional bug, but it would be a confusing one.
export const TARGET_FIELDS = [
  { label: __("Don't import"), value: '' },
  { label: __('Product title'), value: 'title' },
  { label: __('Collection'), value: 'collection' },
  { label: __('Colour'), value: 'color' },
  { label: __('Size'), value: 'size' },
  { label: __('Compare-at price'), value: 'compare_at_price' },
  { label: __('Selling price'), value: 'sale_price' },
  { label: __('Stock'), value: 'stock' },
]

export const REQUIRED_FIELDS = ['title', 'collection', 'color', 'size']

// `open` is deliberately not part of this shape: resetImport() runs from openImport() while the
// dialog is being shown, and clearing `open` there would tear the dialog down as it opens.
function blankImport() {
  return {
    step: 0,
    source: 'csv',
    imagesMode: 'bulk',
    // See importPhase.js: the one value that says what the flow is waiting on.
    phase: 'idle',
    file: null,
    fileUrl: null,
    parsed: false,
    // Photos: every file the browser has uploaded, the merchant's manual pick per file, what the
    // server matched back, and the {group key: [file_url]} map handed to run_import.
    imageFiles: [],
    imageChoices: {},
    imageMatch: null,
    imageAssignments: {},
    reviewFilter: 'all',
    mapping: {},
    confidence: {},
    headers: [],
    rows: [],
    counts: { total: 0, ready: 0, warnings: 0, errors: 0, products: 0 },
    created: [],
    runRowErrors: [],
    runImageErrors: [],
    imagesAttached: 0,
  }
}

export const imp = reactive({ open: false, ...blankImport() })

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
  const { step, source, imagesMode, imageFiles } = imp
  resetImport()
  Object.assign(imp, { step, source, imagesMode, imageFiles })
}

export function openImport() {
  // A run still in flight is shown again rather than reset: its write is landing either way, and
  // the merchant should see what it did.
  if (imp.phase !== 'running' && (imp.phase === 'done' || imp.file)) resetImport()
  imp.open = true
}

export function closeImport() {
  imp.open = false
}

// One action, shared by the Upload preview, "Use suggestions" in Map, and the final commit — a
// dry run when called from validate_import, a real write when called from run_import (see RunStep).
export const validateImportAction = useAdminAction('imports.validate_import')

export function applyValidation(data) {
  imp.headers = data.headers
  imp.mapping = data.mapping
  imp.confidence = data.confidence
  imp.rows = data.rows
  imp.counts = data.counts
  // Photo groups are product + colour, read through the mapping, so a new mapping means the old
  // match may name groups that no longer exist. Images re-matches whenever this is empty.
  imp.imageMatch = null
  imp.imageAssignments = {}
}
