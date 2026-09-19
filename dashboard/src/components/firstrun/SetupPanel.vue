<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import commeraLogo from '../../assets/commera.svg'
import { dismissSetup, skipSetup } from '../../ia/firstRun'
import { REVEAL_EASE, useReveal } from '../../utils/reveal'
import MaximizeIcon from './MaximizeIcon.vue'
import MinimizeIcon from './MinimizeIcon.vue'

const props = defineProps({ steps: { type: Array, required: true } })

const router = useRouter()

// Radius is numeric: frappe-ui's preset drops Tailwind's named scale, so
// `rounded-lg` and bare `rounded` compile to nothing and the corners go square.
const shown = useReveal(150)
const collapsed = ref(false)

const overrides = ref({})

const rows = computed(() =>
  props.steps.map((step) => ({ ...step, done: overrides.value[step.key] ?? step.done })),
)

const doneCount = computed(() => rows.value.filter((step) => step.done).length)
const percent = computed(() => Math.floor((doneCount.value / rows.value.length) * 100))
const allDone = computed(() => doneCount.value === rows.value.length)

function setAll(done) {
  overrides.value = Object.fromEntries(props.steps.map((step) => [step.key, done]))
}

function openStep(step) {
  if (step.done) return
  router.push(step.to)
}
</script>

<template>
  <Teleport to="body">
  <div
    class="fixed right-0 z-40 m-5 mt-[62px] flex w-80 flex-col gap-2 rounded-4 bg-surface-elevation-2 p-3 shadow-2xl transition-all duration-500"
    :class="[
      collapsed ? 'top-[calc(100%-112px)] border border-outline-gray-2' : 'top-0 h-[calc(100%-80px)]',
      shown ? 'translate-x-0 opacity-100' : 'translate-x-4 opacity-0',
    ]"
    :style="{ transitionTimingFunction: REVEAL_EASE }"
  >
    <div class="flex items-center justify-between px-2 py-1.5">
      <p class="text-base font-medium text-ink-gray-9">
        {{ allDone ? 'You are all set' : 'Getting started' }}
      </p>
      <div class="flex gap-1">
        <Button
          variant="ghost"
          :aria-label="collapsed ? 'Expand setup' : 'Collapse setup'"
          @click="collapsed = !collapsed"
        >
          <component :is="collapsed ? MaximizeIcon : MinimizeIcon" class="size-3.5" />
        </Button>
        <Button
          variant="ghost"
          icon="lucide-x"
          aria-label="Close setup"
          @click="dismissSetup"
        />
      </div>
    </div>

    <div v-show="!collapsed" class="flex min-h-0 flex-1 flex-col gap-2.5">
      <div class="mb-3 mt-4 flex flex-col items-center justify-center gap-1">
        <img :src="commeraLogo" alt="" class="mb-4 size-10 shrink-0" />
        <p class="text-base font-medium text-ink-gray-9">Welcome to Commera</p>
        <p class="text-p-base text-ink-gray-7">
          {{ `${doneCount}/${rows.length} steps completed` }}
        </p>
      </div>

      <div class="flex items-center justify-between py-0.5">
        <Badge size="lg" :label="`${percent}% completed`" :theme="allDone ? 'green' : 'amber'" />
        <div class="flex">
          <Button v-if="percent" variant="ghost" label="Reset all" @click="setAll(false)" />
          <Button v-if="!allDone" variant="ghost" label="Skip all" @click="skipSetup" />
        </div>
      </div>

      <div class="flex flex-col gap-1.5 overflow-y-auto">
        <div
          v-for="step in rows"
          :key="step.key"
          class="group flex w-full items-center justify-between gap-2 rounded-1 px-2 py-1.5 hover:bg-surface-gray-1"
          :class="step.done ? '' : 'cursor-pointer'"
          @click="openStep(step)"
        >
          <div
            class="flex items-center gap-2"
            :class="step.done ? 'text-ink-gray-5' : 'text-ink-gray-8'"
          >
            <span :class="[step.icon, 'size-4']" aria-hidden="true" />
            <span class="text-base" :class="step.done && 'line-through'">{{ step.title }}</span>
          </div>
          <Button
            :label="step.done ? 'Reset' : 'Skip'"
            class="hidden !h-4 text-xs !text-ink-gray-6 group-hover:flex"
            @click.stop="overrides[step.key] = !step.done"
          />
        </div>
      </div>
    </div>
  </div>
  </Teleport>
</template>
