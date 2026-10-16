import { toast, useCall } from 'frappe-ui'

// Same shape as dashboard/src/data/api.js: absolute v2 paths, one toast per failure.
const METHOD_PREFIX = '/api/v2/method/'

export function useMethodRead(method, options = {}) {
  const { quiet = false, ...rest } = options
  return useCall({
    url: METHOD_PREFIX + method,
    method: 'GET',
    onError: (error) => !quiet && toast.error(error?.message ?? 'Request failed'),
    ...rest,
  })
}

export function useMethodAction(method, options = {}) {
  const { quiet = false, ...rest } = options
  return useCall({
    url: METHOD_PREFIX + method,
    method: 'POST',
    immediate: false,
    onError: (error) => !quiet && toast.error(error?.message ?? 'Request failed'),
    ...rest,
  })
}
