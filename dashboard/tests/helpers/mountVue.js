import { readFileSync } from 'node:fs'
import { compileScript, parse } from '@vue/compiler-sfc'
import * as Vue from 'vue'

export function loadComponent(path, bindings) {
  const { descriptor } = parse(readFileSync(new URL(`../../src/${path}.vue`, import.meta.url), 'utf8'))
  const script = compileScript(descriptor, { id: path, inlineTemplate: true }).content
    .replace(/import \{([^}]+)\} from ['"]vue['"]/g, (_, names) =>
      `const {${names.replace(/ as /g, ': ')}} = Vue`)
    .replace(/^import [\s\S]*? from ['"][^'"]+['"]\n/gm, '')
    .replace('export default', 'return')
  return new Function('Vue', ...Object.keys(bindings), script)(Vue, ...Object.values(bindings))
}

export const shell = {
  props: ['disabled', 'label'],
  render() {
    return Vue.h('button', { disabled: this.disabled, onClick: this.$attrs.onClick }, [
      this.label, this.$slots.title?.(), this.$slots.actions?.(), this.$slots.default?.(),
    ])
  },
}

export function mount(component) {
  function node(type, text = '') { return { type, text, children: [], props: {} } }
  const renderer = Vue.createRenderer({
    createElement: node, createText: (text) => node('text', text), createComment: () => node('comment'),
    setText: (element, text) => { element.text = text },
    setElementText: (element, text) => { element.text = text },
    patchProp: (element, key, previous, value) => { element.props[key] = value },
    parentNode: (element) => element.parent,
    nextSibling: (element) => element.parent?.children[element.parent.children.indexOf(element) + 1] ?? null,
    insert(element, parent, anchor) {
      element.parent = parent
      const index = anchor ? parent.children.indexOf(anchor) : -1
      if (index < 0) parent.children.push(element)
      else parent.children.splice(index, 0, element)
    },
    remove(element) { element.parent.children.splice(element.parent.children.indexOf(element), 1) },
  })
  const root = node('root')
  const app = renderer.createApp(component)
  app.config.globalProperties.__ = (text) => text
  app.component('RouterLink', shell)
  app.directive('scroll-fade', {})
  app.mount(root)
  return { root, unmount: () => app.unmount() }
}

export function findNode(root, predicate) {
  if (predicate(root)) return root
  for (const child of root.children) {
    const found = findNode(child, predicate)
    if (found) return found
  }
}
