const PAYMENTS_DESCRIPTION = 'Connect payment gateways like Stripe or Razorpay, or configure COD.'

/**
 * The Home setup cards, in the order of a first sale: something to sell, a way to be paid, a way to
 * deliver, then polish. `home` is `home.get_home`'s answer; `domain` is `describeDomains()`'s, and
 * null leaves the domain card out — off Frappe Cloud there is no domain panel to send the owner to.
 */
export function buildHomeTasks(home, domain, siteHost) {
  const tasks = [
    {
      key: 'products',
      title: 'Add your products',
      description: 'Your store has nothing to sell until you add a product and publish it.',
      action: 'Add product',
      route: '/products',
      required: true,
      done: home.tasks.products,
    },
    {
      key: 'payments',
      // With cash on delivery on, the store can already take orders, so gateways are optional.
      title: home.cod_enabled ? 'Take online payments' : 'Set up payments',
      description: PAYMENTS_DESCRIPTION,
      action: 'Set up payments',
      route: '/settings/payments',
      required: !home.cod_enabled,
      done: home.tasks.payments,
    },
    {
      key: 'shipping',
      title: 'Set up shipping',
      description: 'Add delivery options or a shipping rule so checkout can quote delivery.',
      action: 'Set up shipping',
      route: '/settings/shipping',
      required: true,
      done: home.tasks.shipping,
    },
    {
      key: 'brand',
      title: 'Make it look like your brand',
      description: 'Add your logo, a hero image and the menu customers will browse.',
      action: 'Customize theme',
      route: '/storefront/theme',
      done: home.tasks.brand,
    },
  ]
  if (domain) tasks.push(buildDomainTask(domain, siteHost))
  return tasks
}

function buildDomainTask(domain, siteHost) {
  if (domain.status === 'pending') {
    return {
      key: 'domain',
      title: 'Finishing your domain',
      description: `${domain.name} is added. It goes live once DNS and the certificate are ready.`,
      action: 'View status',
      route: '/settings/domains',
      done: false,
    }
  }
  return {
    key: 'domain',
    title: 'Connect a custom domain',
    description: `Use your own address instead of ${siteHost}.`,
    action: 'Connect domain',
    route: '/settings/domains',
    done: domain.status === 'connected',
  }
}

/**
 * Where the store's custom domain has got: `none` until one is added, `pending` until it is the
 * primary domain with a certificate, then `connected`. Null when the domains cannot be read.
 */
export function describeDomains(domains) {
  if (!domains) return null
  const custom = domains.domains.filter((domain) => !domain.is_default)
  const connected = custom.find((domain) => domain.is_primary && domain.tls)
  if (connected) return { status: 'connected', name: connected.domain }
  if (custom.length) return { status: 'pending', name: custom[0].domain }
  return { status: 'none', name: null }
}

// A day old is stale: the thumbnail is the theme's homepage, and products, logo and prices move under it.
export const PREVIEW_MAX_AGE_MS = 24 * 60 * 60 * 1000

/** Whether Home should capture the storefront again: `preview` is `home.get_home`'s `preview`. */
export function needsPreviewCapture(preview, now = Date.now()) {
  if (!preview?.can_capture) return false
  if (!preview.image || !preview.captured_on) return true
  return now - new Date(preview.captured_on.replace(' ', 'T')).getTime() > PREVIEW_MAX_AGE_MS
}
