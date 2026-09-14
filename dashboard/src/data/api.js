// The shared entry point for every screen that reads or writes the real
// commera backend, instead of each screen wiring its own useCall + toast.
// Task-shaped endpoints live under `commera.api.admin.*`,
// so callers pass the path below that prefix, e.g. useAdminRead('catalog.get_products').
import { toast, useCall } from 'frappe-ui'
import { errorMessage } from './errors'

// useCall fetches `baseUrl + url` verbatim — it does NOT prepend the API path. Without the
// absolute prefix the browser resolves the dotted path against the current page, the SPA
// catch-all route serves the shell back, and every screen dies on `Unexpected token '<'`.
// It must be the v2 path: useCall unwraps a response as `data.value?.data`, and reads a
// failure as `errorResponse.errors[0]`. Only /api/v2/ answers in that shape — v1 replies
// `{"message": ...}`, so every read and write silently resolved to null on every screen.
// A request the client itself cancelled — a newer keystroke, a changed filter, an
// unmounted screen — is not a failure the user needs to hear about. Without this,
// every character typed into the search palette raised its own red
// "signal is aborted without reason" toast, twenty deep.
function wasAborted(error) {
  return error?.name === 'AbortError' || /aborted/i.test(error?.message ?? '')
}

const METHOD_PREFIX = '/api/v2/method/'
const ADMIN_MODULE = 'commera.api.admin.'

// A GET read of any whitelisted method, by its full dotted path. Used where the
// dashboard shares an endpoint with the Desk form rather than owning an admin
// wrapper of its own (e.g. the Sales Order refund methods).
// `quiet` opts out of the toast, for a call whose refusal is an expected state
// rather than an error — a subtitle a cashier has no permission to read, or a
// write whose caller already redirects away from the screen.
export function useMethodRead(method, options = {}) {
  const { onError, quiet = false, ...rest } = options
  return useCall({
    url: METHOD_PREFIX + method,
    method: 'GET',
    onError: (error) => {
      if (wasAborted(error)) return
      if (!quiet) toast.error(errorMessage(error))
      onError?.(error)
    },
    ...rest,
  })
}

// A POST write of any whitelisted method, by its full dotted path.
export function useMethodAction(method, options = {}) {
  const { onError, quiet = false, ...rest } = options
  return useCall({
    url: METHOD_PREFIX + method,
    method: 'POST',
    immediate: false,
    onError: (error) => {
      if (wasAborted(error)) return
      if (!quiet) toast.error(errorMessage(error))
      onError?.(error)
    },
    ...rest,
  })
}

// A GET read. Every list/detail screen fetches the same way, and a failure
// surfaces the same way — as a toast, not a silently empty screen.
export function useAdminRead(path, options = {}) {
  return useMethodRead(ADMIN_MODULE + path, options)
}

// A POST write. `immediate` defaults to false — a write fires on `.submit()`,
// never on mount — and a failure toasts here so no screen has to remember to.
export function useAdminAction(path, options = {}) {
  return useMethodAction(ADMIN_MODULE + path, options)
}
