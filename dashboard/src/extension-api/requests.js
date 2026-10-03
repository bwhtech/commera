import { getCurrentInstance, inject } from 'vue'
import { useMethodAction as useDashboardMethodAction } from '../data/api'
import { ACTION_CONTEXT } from './context'

// Inside an action dialog a thrown error is shown under the form, so the toast would say it a second time.
export function useMethodAction(method, options = {}) {
  const insideAction = Boolean(getCurrentInstance() && inject(ACTION_CONTEXT, null))
  return useDashboardMethodAction(method, { quiet: insideAction, ...options })
}
