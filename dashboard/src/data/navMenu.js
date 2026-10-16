import { computed, ref } from 'vue'
import { createAdminCaller } from './adminCaller'

const menu = ref([])
const maxDepth = ref(0)
const selectedName = ref(null)
const revision = ref(0)
const expandedKeys = ref([])

// A refused read leaves `menu` empty, which reads as "this store has no menu" unless the failure is kept.
const loadError = ref(null)

const { attempt, call, loading } = createAdminCaller('navigation.')

function walk(nodes, visit, depth = 1) {
  for (const node of nodes) {
    visit(node, depth)
    walk(node.children, visit, depth + 1)
  }
}

function findNode(name, nodes = menu.value) {
  if (!name) return null
  for (const node of nodes) {
    if (node.name === name) return node
    const found = findNode(name, node.children)
    if (found) return found
  }
  return null
}

const selected = computed(() => findNode(selectedName.value))

// Levels hanging below a node — 0 for a leaf, so a node with children only is 1.
function subtreeHeight(node) {
  if (!node.children.length) return 0
  return 1 + Math.max(...node.children.map(subtreeHeight))
}

// Depth a node currently sits at, counting a top-level tab as 1.
function depthOf(name) {
  let depth = 0
  walk(menu.value, (node, nodeDepth) => {
    if (node.name === name) depth = nodeDepth
  })
  return depth
}

// The server throws past `max_depth`, so the tree refuses the drop rather than
// animating a move that is about to be snapped back.
function canNest(node, parentDepth) {
  return parentDepth + 1 + subtreeHeight(node) <= maxDepth.value
}

// Every mutation replaces the whole tree, so without this, moving one entry collapses the branch being worked in.
function keepExpansion(nodes) {
  const known = new Set()
  walk(menu.value, (node) => known.add(node.name))
  const open = new Set(expandedKeys.value)
  const next = []
  walk(nodes, (node, depth) => {
    if (known.has(node.name) ? open.has(node.name) : depth === 1) next.push(node.name)
  })
  expandedKeys.value = next
}

function apply(data) {
  if (!data?.menu) return

  keepExpansion(data.menu)
  menu.value = data.menu
  if (data.max_depth) maxDepth.value = data.max_depth

  // A deleted node must not stay selected — the inspector would render a stale copy
  // of a row that is no longer in the tree.
  if (selectedName.value && !findNode(selectedName.value)) selectedName.value = null
}

// The nodes from the top level down to `name`, or none when it is not in the tree.
function pathTo(name, nodes = menu.value) {
  for (const node of nodes) {
    if (node.name === name) return [node]
    const below = pathTo(name, node.children)
    if (below.length) return [node, ...below]
  }
  return []
}

// `revealUnder` opens the branch a row was added to or moved into: the refresh otherwise
// restores that branch's remembered collapsed state, so the change lands on the server
// yet looks like nothing happened.
async function mutate(method, params = {}, revealUnder = '') {
  const data = await call(method, params)
  if (!data) return null
  apply(data)
  const revealed = pathTo(revealUnder).map((node) => node.name)
  expandedKeys.value = [...new Set([...expandedKeys.value, ...revealed])]
  // Every menu change funnels through here, so this is the one place the storefront
  // preview is told it is stale.
  revision.value += 1
  return data
}

async function load() {
  const { data, error } = await attempt('get_editor_data')
  loadError.value = error
  apply(data)
}

export function useNavMenu() {
  return {
    menu,
    expandedKeys,
    maxDepth,
    loadError,
    revision,
    selectedName,
    selected,
    loading,
    load,
    call,
    mutate,
    findNode,
    depthOf,
    canNest,
  }
}
