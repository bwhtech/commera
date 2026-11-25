import { PLACEHOLDER_OPTION, PLACEHOLDER_SIZE } from './product.js'

// The colour x size matrix the Add product dialog collects, in the shape
// catalog.create_product expects: [{ option, sizes }].

// Colour + size pairs, keyed for a Set. A NUL cannot appear in an attribute value, so it joins safely.
export function pairKey(option, size) {
  return `${option}\u0000${size}`
}

// The grid stores what the owner UNticked, not what they ticked, so a colour or size added later
// arrives selected everywhere without a second pass over the existing choices.
export function buildOptionSizes(options, sizes, excluded) {
  const dropped = new Set(excluded)
  return options.map((option) => ({
    option,
    sizes: sizes.filter((size) => !dropped.has(pairKey(option, size))),
  }))
}

export function optionChanges({ live, options, sizes, excluded, keepsHiddenOption }) {
  const rowOptions = options.length || !keepsHiddenOption ? options : [PLACEHOLDER_OPTION]
  const rowSizes = sizes.length ? sizes : [PLACEHOLDER_SIZE]
  const ticked = buildOptionSizes(rowOptions, rowSizes, excluded).flatMap((row) =>
    row.sizes.map((size) => ({ option: row.option, size })),
  )
  const liveKeys = new Set(live.map((pair) => pairKey(pair.option, pair.size)))
  const tickedKeys = new Set(ticked.map((pair) => pairKey(pair.option, pair.size)))
  return {
    ticked,
    added: ticked.filter((pair) => !liveKeys.has(pairKey(pair.option, pair.size))),
    removed: live.filter((pair) => !tickedKeys.has(pairKey(pair.option, pair.size))),
  }
}
