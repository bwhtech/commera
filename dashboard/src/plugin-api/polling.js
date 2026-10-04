import { onScopeDispose } from 'vue'

export function usePolling(request, { every = 5000, while: shouldPoll = () => true } = {}) {
  const timer = setInterval(() => {
    if (document.hidden || request.loading || !shouldPoll()) return
    request.reload()
  }, every)
  onScopeDispose(() => clearInterval(timer))
}
