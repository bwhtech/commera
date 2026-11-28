import { ref } from 'vue'
import { trySubmit, useAdminAction, useAdminRead } from './api'
import { errorMessage } from './errors'
import { __ } from './translation'
import { beginPhase, endPhase, imp, isCurrentImport } from './importFlow'
import { isRunSettled, itemCodesToImport, preselectedCodes } from './erpnextImportState'
import { setupPollDelay } from '../ia/onboardingSteps'

const previewParams = ref({})
export const previewRequest = useAdminRead('erpnext_import.get_erpnext_import_preview', {
  immediate: false,
  quiet: true,
  params: () => previewParams.value,
})

const itemCodesParams = ref({})
const itemCodesRequest = useAdminRead('erpnext_import.get_erpnext_import_preview', {
  immediate: false,
  params: () => itemCodesParams.value,
})

const statusRequest = useAdminRead('erpnext_import.get_erpnext_import_status', {
  immediate: false,
  quiet: true,
  params: () => ({ job_id: imp.erpnext.jobId }),
})

export const startAction = useAdminAction('erpnext_import.start_erpnext_import', { quiet: true })
export const publishAction = useAdminAction('erpnext_import.publish_imported_products')

const ITEM_CODES_PAGE = 500

export async function loadErpnextPreview() {
  const { search, page, pageSize } = imp.erpnext
  previewParams.value = { search: search || undefined, start: (page - 1) * pageSize, page_length: pageSize }
  const data = await previewRequest.fetch()
  if (!data) return
  // A slower, older search can answer last; keep only the answer for what the box holds now.
  if ((search || '') !== (imp.erpnext.search || '')) return
  imp.erpnext.items = data.items
  imp.erpnext.itemsSearch = search || ''
  imp.erpnext.skipped = data.skipped
  imp.erpnext.total = data.total
  if (!search) imp.erpnext.importableCount = data.total
}

export async function loadErpnextSelection() {
  if (imp.erpnext.selectionReady) return
  const items = []
  while (true) {
    itemCodesParams.value = { start: items.length, page_length: ITEM_CODES_PAGE }
    const data = await itemCodesRequest.fetch()
    if (!data) return
    items.push(...data.items)
    if (!data.items.length || items.length >= data.total) break
  }
  imp.erpnext.importableCount = items.length
  imp.erpnext.allItemCodes = items.map((item) => item.item_code)
  imp.erpnext.selected = preselectedCodes(items)
  imp.erpnext.selectionReady = true
}

let pollTimer = null
let pollStartedAt = 0
let pollTicket = null

function schedulePoll() {
  const delay = setupPollDelay(Date.now() - pollStartedAt)
  if (delay === null) {
    imp.erpnext.poll = 'stalled'
    return
  }
  pollTimer = setTimeout(async () => {
    pollTimer = null
    const status = await statusRequest.fetch()
    if (!isCurrentImport(pollTicket)) return
    if (status) imp.erpnext.status = status
    if (status && isRunSettled(status.status)) {
      imp.erpnext.poll = 'off'
      endPhase(pollTicket, status.status)
      return
    }
    schedulePoll()
  }, delay)
}

export function resumeErpnextPolling() {
  if (pollTimer || imp.phase !== 'running') return
  pollStartedAt = Date.now()
  imp.erpnext.poll = 'polling'
  schedulePoll()
}

export async function startErpnextImport() {
  const ticket = beginPhase('running')
  if (ticket === null) return
  imp.erpnext.status = null
  imp.erpnext.error = ''
  imp.erpnext.otherImportRunning = false
  imp.erpnext.published = null

  const itemCodes = itemCodesToImport(imp.erpnext.selected, imp.erpnext.importableCount)
  const started = await trySubmit(startAction, itemCodes ? { item_codes: itemCodes } : {})
  if (!isCurrentImport(ticket)) return
  if (!started) {
    imp.erpnext.error = errorMessage(startAction.error, __('The import could not start. Try again in a moment.'))
    imp.erpnext.otherImportRunning = startAction.error?.type === 'ImportAlreadyRunningError'
    endPhase(ticket, 'failed')
    return
  }
  imp.erpnext.jobId = startAction.data.job_id
  imp.erpnext.log = startAction.data.log
  pollTicket = ticket
  resumeErpnextPolling()
}

export async function publishErpnextImport() {
  if (imp.erpnext.published || publishAction.loading) return
  if (await trySubmit(publishAction, { log: imp.erpnext.log })) imp.erpnext.published = publishAction.data
}
