// Shared by both modules: the kit splits it into one hashed chunk.
export const ATTENTION_STATES = new Set(['failed', 'canceled', 'onhold'])
export const statusTheme = (status) => (ATTENTION_STATES.has(status) ? 'red' : 'green')
