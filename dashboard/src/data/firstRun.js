// `done` is not wired to the server yet — no endpoint reports setup state.
export const SETUP_STEPS = [
  {
    key: 'product',
    icon: 'lucide-package',
    title: 'Add your first product',
    note: 'Photos, price and stock',
    action: 'Add product',
    to: '/products',
  },
  {
    key: 'payments',
    icon: 'lucide-credit-card',
    title: 'Connect a payment gateway',
    note: 'Razorpay, Stripe or cash on delivery',
    action: 'Connect',
    to: '/settings/payments',
  },
  {
    key: 'shipping',
    icon: 'lucide-truck',
    title: 'Set up shipping',
    note: 'Rates, zones and a pickup address',
    action: 'Set up',
    to: '/settings/shipping',
  },
  {
    key: 'theme',
    icon: 'lucide-palette',
    title: 'Pick a theme',
    note: 'Make the storefront look like your brand',
    action: 'Browse themes',
    to: '/storefront/theme',
  },
]

export function stepsWithProgress(doneCount) {
  return SETUP_STEPS.map((step, index) => ({ ...step, done: index < doneCount }))
}
