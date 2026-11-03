// The product import flow: shared state for one run of it. Every step reads and writes the real
// commera.api.admin.imports endpoints — the spreadsheet is the only source that exists, and photos
// are matched to a product colour by file name (imports.match_import_images).
import { reactive } from 'vue'
import { useAdminAction } from './api'
import { useTelemetry } from '../telemetry'

const telemetry = useTelemetry()

export const STEPS = [
  { key: 'source', label: 'Source', icon: 'lucide-plug', hint: 'Where the products live today' },
  { key: 'upload', label: 'Upload', icon: 'lucide-file-up', hint: 'Your spreadsheet' },
  { key: 'map', label: 'Match columns', icon: 'lucide-arrow-left-right', hint: 'Your headings to ours' },
  { key: 'images', label: 'Images', icon: 'lucide-image', hint: 'Photos for each product' },
  { key: 'review', label: 'Review', icon: 'lucide-list-checks', hint: 'Check before saving' },
  { key: 'run', label: 'Import', icon: 'lucide-rocket', hint: 'Create everything' },
]

// TARGET_FIELDS/REQUIRED mirror commera.api.admin.imports.FIELD_SYNONYMS/REQUIRED_FIELDS field
// for field — a mismatch here means a column that maps cleanly on the server shows the wrong
// label here, not a functional bug, but it would be a confusing one.
export const TARGET_FIELDS = [
  { label: "Don't import", value: '' },
  { label: 'Product title', value: 'title' },
  { label: 'Collection', value: 'collection' },
  { label: 'Colour', value: 'color' },
  { label: 'Size', value: 'size' },
  { label: 'Compare-at price', value: 'compare_at_price' },
  { label: 'Selling price', value: 'sale_price' },
  { label: 'Stock', value: 'stock' },
]

export const REQUIRED_FIELDS = ['title', 'collection', 'color', 'size']

// `open` is deliberately not part of this shape: resetImport() runs from openImport() while the
// dialog is being shown, and clearing `open` there would tear the dialog down as it opens.
function blankImport() {
  return {
    step: 0,
    source: 'csv',
    imagesMode: 'bulk',
    file: null,
    fileUrl: null,
    parsing: false,
    parsed: false,
    // Photos: every file the browser has uploaded, the merchant's manual pick per file, what the
    // server matched back, and the {group key: [file_url]} map handed to run_import.
    imageFiles: [],
    imageChoices: {},
    imageMatch: null,
    imageAssignments: {},
    running: false,
    // `finished` means the write landed; a refused run sets `failed` instead, so that a retry is
    // not mistaken for a completed import (see RunStep).
    finished: false,
    failed: false,
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

export function resetImport() {
  Object.assign(imp, blankImport())
}

// `surface` is docs/telemetry.md's `products_import_opened.surface`: where the owner opened it from.
export function openImport(surface) {
  if (imp.finished || imp.file) resetImport()
  imp.open = true
  telemetry.capture('products_import_opened', { surface })
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
}
