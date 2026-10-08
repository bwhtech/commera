// The Vite dev server serves index.html, not the Jinja-rendered commera.html, so no boot keys reach `window`.
if (import.meta.env.DEV) {
  const response = await fetch('/api/method/commera.www.commera.get_context_for_dev', {
    headers: { Accept: 'application/json' },
  })
  const isGuest = !document.cookie.split('; ').some((cookie) => cookie.startsWith('user_id=') && cookie !== 'user_id=Guest')
  if (response.ok) Object.assign(window, (await response.json()).message)
  else if (isGuest) {
    window.location.replace(`/login?redirect-to=${encodeURIComponent(window.location.pathname)}`)
    // Holds the shell back so it never mounts and fires requests as Guest while the browser navigates away.
    await new Promise(() => {})
  } else console.error('[commera] dev boot failed: turn on developer_mode, or use a user with dashboard access', response.status)
}
