<script setup>
import { computed, ref } from 'vue'
import { Button, ErrorMessage, FormControl } from 'frappe-ui'
import { marketStore } from '../../../data/markets'
import { __ } from '../../../data/translation'

const props = defineProps({
  countries: { type: Array, required: true },
  handle: { type: String, required: true },
  isPrimary: { type: Boolean, default: false },
  error: { type: String, default: '' },
})

const emit = defineEmits(['update'])

// A country another market has stays pickable: the server's refusal names that market on this field.
const options = computed(() => {
  const owners = marketStore.ownersExcept(props.handle)
  return (marketStore.choices.value?.countries ?? [])
    .filter((country) => !props.countries.includes(country.name))
    .map((country) => {
      const owner = owners.get(country.name)
      return { label: owner ? __('{0} (in {1})', [country.name, owner]) : country.name, value: country.name }
    })
})

// The picker is only a way to add one: re-rendered empty after each pick.
const pickerKey = ref(0)

function add(country) {
  if (!country) return
  pickerKey.value += 1
  emit('update', [...props.countries, country])
}

function remove(country) {
  emit('update', props.countries.filter((name) => name !== country))
}
</script>

<template>
  <section class="space-y-4">
    <h3 class="text-base font-semibold text-ink-gray-8">{{ __('Countries') }}</h3>
    <p v-if="isPrimary" class="text-p-sm text-ink-gray-5">{{ __('All countries no other market has.') }}</p>
    <div v-else>
      <div v-if="countries.length" class="flex flex-wrap gap-1.5">
        <Button
          v-for="country in countries"
          :key="country"
          size="sm"
          variant="subtle"
          :label="country"
          icon-right="lucide-x"
          :aria-label="__('Remove {0}', [country])"
          @click="remove(country)"
        />
      </div>
      <p v-else class="text-p-sm text-ink-gray-5">{{ __('Add at least one country.') }}</p>
      <FormControl
        :key="pickerKey"
        class="mt-3 sm:w-72"
        type="combobox"
        :model-value="null"
        :options="options"
        :placeholder="__('Add a country…')"
        :aria-label="__('Add a country')"
        @update:model-value="add"
      />
      <ErrorMessage v-if="error" class="mt-2" :message="error" />
    </div>
  </section>
</template>
