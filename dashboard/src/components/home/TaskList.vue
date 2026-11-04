<script setup>
import EmptyState from '../EmptyState.vue'
import TaskCard from './TaskCard.vue'

defineProps({
  tasks: { type: Array, required: true },
  store: { type: Object, required: true },
})
defineEmits(['dismiss'])

// A leaving card goes absolute so its neighbours slide into the gap while it fades, instead of
// snapping once it is gone. Pin its box first: absolute alone would shrink it to its content width
// and jump it to the grid's corner. The grid is `relative` for this.
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
    tag="div"
    class="relative grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3"
    move-class="transition-transform duration-300 ease-in-out-strong motion-reduce:transition-none"
    enter-active-class="transition-[opacity,transform] duration-200 ease-out-strong"
    enter-from-class="scale-[0.97] opacity-0 motion-reduce:scale-100"
    leave-active-class="absolute transition-[opacity,transform] duration-150 ease-out-strong"
    leave-to-class="scale-[0.97] opacity-0 motion-reduce:scale-100"
    @before-leave="pinBeforeLeave"
  >
    <TaskCard v-for="task in tasks" :key="task.key" :task="task" :store="store" @dismiss="$emit('dismiss', task.key)" />
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
