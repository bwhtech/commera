<script setup>
import { ref } from 'vue'
import { KeyboardShortcut, SidebarItem, SidebarLabel } from 'frappe-ui'

const props = defineProps({
  section: { type: Object, required: true },
  activeTarget: { type: String, default: undefined },
})

// A parent row is a disclosure, not a destination. It opens itself when the
// route lands inside it, and stays wherever you last put it otherwise.
const opened = ref({})

const holdsRoute = (item) => item.children.some((child) => child.to === props.activeTarget)
const isOpen = (item) => opened.value[item.to] ?? holdsRoute(item)
const toggle = (item) => (opened.value[item.to] = !isOpen(item))
</script>

<template>
  <div class="pt-1.5 first:pt-0">
    <SidebarLabel v-if="section.label" divider>{{ section.label }}</SidebarLabel>

    <div class="space-y-0.5">
      <template v-for="item in section.items" :key="item.to ?? item.label">
        <!-- Parent + reports. -->
        <template v-if="item.children">
          <SidebarItem
            :label="item.label"
            :icon="item.icon"
            :active="!isOpen(item) && holdsRoute(item)"
            @click="toggle(item)"
          >
            <template #suffix>
              <span
                class="lucide-chevron-down mr-1 size-3.5 text-ink-gray-5 transition-transform"
                :class="isOpen(item) ? '' : '-rotate-90'"
                aria-hidden="true"
              />
            </template>
          </SidebarItem>
          <div v-show="isOpen(item)" class="space-y-0.5 pl-5">
            <SidebarItem
              v-for="child in item.children"
              :key="child.to"
              :label="child.label"
              :icon="child.icon"
              :to="child.to"
              :active="child.to === activeTarget"
            />
          </div>
        </template>

        <!-- An item without `to` is an action row (Search); it opens an overlay
             rather than routing, so it never takes active state. -->
        <SidebarItem
          v-else
          :label="item.label"
          :icon="item.icon"
          :to="item.to"
          :suffix="item.shortcut ? undefined : item.suffix"
          :active="Boolean(item.to) && item.to === activeTarget"
          @click="item.onClick?.()"
        >
          <template v-if="item.shortcut" #suffix>
            <KeyboardShortcut class="mr-1" :combo="item.shortcut" />
          </template>
        </SidebarItem>
      </template>
    </div>
  </div>
</template>
