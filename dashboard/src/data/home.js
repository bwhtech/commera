import { language } from './boot.js'
import { __ } from './translation.js'

// A null `domain` leaves the domain card out: off Frappe Cloud there is no domain panel to send the owner to.
export function buildHomeTasks(home, domain, siteHost) {
  const tasks = [
    {
      key: 'products',
      noun: __('products'),
      title: __('Add your products'),
      description: __('Your store has nothing to sell until you add a product and publish it.'),
      action: __('Add product'),
      route: '/products',
      required: true,
      done: home.tasks.products,
    },
    {
      key: 'payments',
      noun: __('payments'),
      title: home.cod_enabled ? __('Take online payments') : __('Set up payments'),
      description: __('Connect payment gateways like Stripe or Razorpay, or configure COD.'),
      action: __('Set up payments'),
      route: '/settings/payments',
      required: !home.cod_enabled,
      done: home.tasks.payments,
    },
    {
      key: 'shipping',
      noun: __('shipping'),
      title: __('Set up shipping'),
      description: __('Add delivery options or a shipping rule so checkout can quote delivery.'),
      action: __('Set up shipping'),
      route: '/settings/shipping',
      required: true,
      done: home.tasks.shipping,
    },
    {
      key: 'brand',
      title: __('Make it look like your brand'),
      description: __('Add your logo, a hero image and the menu customers will browse.'),
      action: __('Customize theme'),
      route: '/storefront/theme',
      done: home.tasks.brand,
    },
  ]
  if (domain) tasks.push(buildDomainTask(domain, siteHost))
  return tasks
}

function buildDomainTask(domain, siteHost) {
  if (domain.status === 'ready') {
    return {
      key: 'domain',
      title: __('Make your domain primary'),
      description: __('{0} is connected. Make it the primary domain so shoppers land on it.', [domain.name]),
      action: __('Open domains'),
      route: '/settings/domains',
      done: false,
    }
  }
  if (domain.status === 'pending') {
    return {
      key: 'domain',
      title: __('Finishing your domain'),
      description: __('{0} is added. It goes live once DNS and the certificate are ready.', [domain.name]),
      action: __('View status'),
      route: '/settings/domains',
      done: false,
    }
  }
  return {
    key: 'domain',
    title: __('Connect a custom domain'),
    description: __('Use your own address instead of {0}.', [siteHost]),
    action: __('Connect domain'),
    route: '/settings/domains',
    done: domain.status === 'connected',
  }
}

export function describeDomains(domains) {
  if (!domains) return null
  const custom = domains.domains.filter((domain) => !domain.is_default)
  const connected = custom.find((domain) => domain.is_primary && domain.tls)
  if (connected) return { status: 'connected', name: connected.domain }
  const ready = custom.find((domain) => domain.tls)
  if (ready) return { status: 'ready', name: ready.domain }
  if (custom.length) return { status: 'pending', name: custom[0].domain }
  return { status: 'none', name: null }
}

export const PREVIEW_MAX_AGE_MS = 24 * 60 * 60 * 1000

export function needsPreviewCapture(preview, now = Date.now()) {
  if (!preview?.can_capture) return false
  if (!preview.image || !preview.captured_on) return true
  return now - new Date(preview.captured_on).getTime() > PREVIEW_MAX_AGE_MS
}

const LIST = new Intl.ListFormat([language, 'en'], { type: 'conjunction' })

export function listBlockers(tasks) {
  return LIST.format(tasks.map((task) => task.noun))
}

export function storeSlug(storeName) {
  return (storeName ?? '').toLowerCase().replace(/[^a-z0-9]+/g, '') || 'yourstore'
}

export function describeStoreStatus(isLive, blockerCount) {
  if (isLive) {
    return {
      dot: null,
      label: null,
      headline: __('Your store is open for business'),
      subline: __('Here is what will make your store even better.'),
    }
  }
  const headline = __('Your store is taking shape')
  if (blockerCount) {
    return {
      dot: 'bg-surface-amber-7',
      label: blockerCount === 1 ? __('1 step before you can sell') : __('{0} steps before you can sell', [blockerCount]),
      headline,
      subline: __('Finish the essentials, then publish when you are ready.'),
    }
  }
  return {
    dot: 'bg-surface-gray-5',
    label: __('Ready to publish'),
    headline,
    subline: __('You can take orders now. Publish to open the doors.'),
  }
}
