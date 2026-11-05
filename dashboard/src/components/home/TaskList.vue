<script setup>
import { nextTick, useTemplateRef } from 'vue'
import EmptyState from '../EmptyState.vue'
import TaskCard from './TaskCard.vue'

const props = defineProps({
  tasks: { type: Array, required: true },
  store: { type: Object, required: true },
})
const emit = defineEmits(['dismiss'])
const list = useTemplateRef('list')

// The dismissed card takes the focused button with it; hand focus to a neighbour instead of <body>.
async function dismiss(index) {
  const neighbour = props.tasks[index + 1] ?? props.tasks[index - 1]
  emit('dismiss', props.tasks[index].key)
  await nextTick()
  if (neighbour) list.value?.$el.querySelector(`[data-task="${neighbour.key}"] button`)?.focus()
}

// A leaving card goes absolute; pin its box first or it shrinks to its content and jumps to the grid's corner.
function pinBeforeLeave(element) {
  Object.assign(element.style, {
    width: `${element.offsetWidth}px`,
    height: `${element.offsetHeight}px`,
    left: `${element.offsetLeft}px`,
    top: `${element.offsetTop}px`,
  })
}
</script>

<template>
  <TransitionGroup
    v-if="tasks.length"
    ref="list"
    tag="div"
    class="relative grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3"
    move-class="transition-transform duration-300 ease-in-out-strong motion-reduce:transition-none"
    enter-active-class="transition-[opacity,transform] duration-200 ease-out-strong"
    enter-from-class="scale-[0.97] opacity-0 motion-reduce:scale-100"
    leave-active-class="absolute transition-[opacity,transform] duration-150 ease-out-strong"
    leave-to-class="scale-[0.97] opacity-0 motion-reduce:scale-100"
    @before-leave="pinBeforeLeave"
  >
    <TaskCard
      v-for="(task, index) in tasks"
      :key="task.key"
      :data-task="task.key"
      :task="task"
      :store="store"
      @dismiss="dismiss(index)"
    />
  </TransitionGroup>

  <div v-else class="rounded-6 border border-dashed border-outline-gray-2 py-6">
    <EmptyState
      icon="lucide-party-popper"
      title="You are all caught up"
      description="New suggestions show up here as your store grows."
      compact
    />
  </div>
</template>
