import { openSettings } from '../ia/settings'
import { useMethodAction } from './api'
import { openLanguagePicker } from '../ia/languagePicker'
import { isAdmin } from './boot'
import { __ } from './translation'

// The storefront is served by this same site, so it is the origin's root — a
// bare '/' redirects to the shopper's language.
function openStorefront() {
  window.open('/', '_blank', 'noopener')
}

// What the desktop store menu and the phone's More sheet both offer: the things that
// are about the account, not about the page you are on.
export function useAccountMenu() {
  const logoutAction = useMethodAction('logout', { quiet: true })

  // `location.replace` rather than a router push: the session cookie is gone
  // server-side, so the shell in memory is authenticated against nothing and
  // every subsequent read would 403 behind a screen that still looks logged in.
  async function logout() {
    // The redirect runs either way: a logout that failed still leaves a shell whose
    // session may be gone, and stranding the merchant on it is worse than sending
    // them to a login page they can retry from.
    await logoutAction.submit().catch(() => {})
    window.location.replace('/login')
  }

  // The language is the admin's own, so staff without Settings still get to pick it.
  const languageItem = { label: __('Language'), icon: 'lucide-languages', onClick: openLanguagePicker }
  const logoutItem = { label: __('Log out'), icon: 'lucide-log-out', onClick: logout }
  if (!isAdmin) return [languageItem, logoutItem]

  return [
    { label: __('Settings'), icon: 'lucide-settings', onClick: () => openSettings() },
    { label: __('Appearance'), icon: 'lucide-sun-moon', onClick: () => openSettings('appearance') },
    languageItem,
    { label: __('View storefront'), icon: 'lucide-external-link', onClick: openStorefront },
    logoutItem,
  ]
}
