import { watch } from 'vue'
import { settings as settingsState } from './settingsRoute'
import { isCloudBillingAvailable } from '../data/cloudBilling'
import { isCloudDomainsAvailable } from '../data/cloudDomains'
import { __ } from '../data/translation'
import { pluginSettingsTabs } from './plugins'

// Derived from the URL in ia/settingsRoute; re-exported because this is still the door the
// rest of the app knocks on.
export { openSettings, settings } from './settingsRoute'

// The dialog keeps its panels mounted while hidden (`unmount-on-hide=false`), so a panel's
// drill-in state — an open webhook, a warehouse's address form, a provider being configured —
// would greet the next open where the last one left off. A panel hands its reset here, and it runs
// each time the dialog closes. Called from a component's setup, so the watch ends with it.
export function onSettingsClose(reset) {
  watch(
    () => settingsState.open,
    (isOpen) => {
      if (!isOpen) reset()
    },
  )
}

// `value` must stay identical to AppSettingsDialog's SettingsNavItem values. The palette
// matches a plain substring per keyword — no tokenising — so list the words people type.
export const SETTINGS_TABS = [
  {
    value: 'general',
    label: __('General'),
    icon: 'lucide-store',
    keywords: ['store', 'shop', 'name', 'address', 'currency', 'timezone', 'contact', 'company'],
  },
  {
    value: 'appearance',
    label: __('Appearance'),
    icon: 'lucide-sun-moon',
    keywords: ['theme', 'dark', 'light', 'colour', 'color', 'logo', 'brand'],
  },
  {
    value: 'emails',
    label: __('Emails'),
    icon: 'lucide-mail',
    keywords: ['email', 'template', 'order confirmation', 'cancellation', 'back in stock', 'notification'],
  },
  {
    value: 'languages',
    label: __('Languages'),
    icon: 'lucide-languages',
    keywords: ['language', 'languages', 'locale', 'default language', 'publish', 'right to left', 'rtl', 'arabic'],
  },
  {
    value: 'markets',
    label: __('Markets'),
    icon: 'lucide-globe',
    keywords: ['market', 'markets', 'country', 'countries', 'currency', 'price list', 'region', 'international', 'tax'],
  },
  {
    value: 'translations',
    label: __('Translations'),
    icon: 'lucide-languages',
    keywords: ['translation', 'translate', 'language', 'locale', 'csv', 'export', 'import', 'arabic'],
  },
  {
    value: 'payments',
    label: __('Payments'),
    icon: 'lucide-credit-card',
    keywords: ['stripe', 'razorpay', 'upi', 'card', 'keys', 'gateway', 'checkout', 'cash on delivery', 'cod', 'refund'],
  },
  {
    value: 'shipping',
    label: __('Shipping'),
    icon: 'lucide-truck',
    keywords: ['carrier', 'shiprocket', 'aftership', 'rates', 'courier', 'delivery', 'tracking', 'free shipping'],
  },
  {
    value: 'locations',
    label: __('Pickup locations'),
    icon: 'lucide-map-pin',
    keywords: ['pickup', 'warehouse', 'collect', 'store pickup', 'branch', 'address'],
  },
  {
    value: 'checkout',
    label: __('Checkout'),
    icon: 'lucide-shopping-cart',
    keywords: ['checkout', 'guest', 'guest checkout', 'order link', 'track order', 'without account'],
  },
  {
    value: 'apps',
    label: __('Analytics'),
    icon: 'lucide-chart-line',
    keywords: ['ga4', 'google analytics', 'pixel', 'tracking', 'meta', 'apps', 'integrations'],
  },
  {
    value: 'plugins',
    label: __('Plugins'),
    icon: 'lucide-blocks',
    keywords: ['plugins', 'apps', 'installed', 'deliveries', 'failed', 'retry'],
  },
  {
    value: 'webhooks',
    label: __('Webhooks'),
    icon: 'lucide-webhook',
    keywords: ['webhooks', 'headless', 'storefront', 'events', 'endpoint', 'signing secret', 'hmac', 'integration'],
  },
  {
    value: 'advanced',
    label: __('Advanced'),
    icon: 'lucide-sliders-horizontal',
    keywords: ['developer', 'api', 'reset', 'danger', 'cache', 'debug'],
  },
  // Only on a Frappe Cloud v2 site, for a System Manager: elsewhere /settings/billing falls
  // back to General and the palette never offers it.
  ...(isCloudBillingAvailable
    ? [
        {
          value: 'billing',
          label: __('Billing'),
          icon: 'lucide-receipt',
          keywords: ['billing', 'plan', 'subscription', 'invoice', 'payment method', 'trial', 'frappe cloud'],
        },
      ]
    : []),
  ...(isCloudDomainsAvailable
    ? [
        {
          value: 'domains',
          label: __('Domains'),
          icon: 'lucide-globe',
          keywords: ['domain', 'custom domain', 'dns', 'ssl', 'certificate', 'url', 'address', 'frappe cloud'],
        },
      ]
    : []),
  // Each installed plugin's own tab, appended so the search palette finds them as well.
  ...pluginSettingsTabs(),
]
