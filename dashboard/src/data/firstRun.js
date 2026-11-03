// The setup checklist's shape, with no imports so tests/unit can load it under plain node. Which
// steps are done is the server's answer (data/setupState.js), the same facts the milestones read.
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

// `state` is get_setup_state's answer: one boolean per step key.
export function stepsFromState(state) {
  return SETUP_STEPS.map((step) => ({ ...step, done: state?.[step.key] === true }))
}

// docs/telemetry.md's `steps_done`, 0 to 4.
export function countStepsDone(state) {
  return stepsFromState(state).filter((step) => step.done).length
}
