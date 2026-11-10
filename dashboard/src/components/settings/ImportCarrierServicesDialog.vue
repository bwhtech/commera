<script setup>
/**
 * The services a connected carrier actually sells, picked from a list.
 *
 * A service code is the carrier's own string — an account id and a service type welded
 * together — and a typo in one fails quietly at checkout: the option is never quoted and
 * simply does not appear. So the codes are read from the carrier rather than typed, and
 * this dialog exists so nobody has to know what one looks like.
 *
 * The carrier answers grouped by shipper account, because an account is what it bills a
 * label against, and the same service type under two accounts is two different codes.
 */
import { computed, ref, watch } from 'vue'
import {
  Button,
  Checkbox,
  Dialog,
  ErrorMessage,
  FormControl,
  ScrollArea,
  Skeleton,
  toast,
} from 'frappe-ui'
import EmptyState from '../EmptyState.vue'
import { __ } from '../../data/translation'
import { createSequence } from '../../utils/sequence'

const props = defineProps({
  // { provider, label } of the carrier being imported from; null while closed.
  provider: { type: Object, default: null },
  fetchChoices: { type: Function, required: true },
  submit: { type: Function, required: true },
})

const open = defineModel('open', { type: Boolean, required: true })

const accounts = ref([])
const selectedCodes = ref([])
const backupCharge = ref('0')
const loading = ref(false)
// A carrier that publishes nothing and a carrier that refused the question look the same
// on screen unless the failure is kept.
const failed = ref(false)
const importing = ref(false)

// A stack of identical bars reads as a progress bar rather than as a list of names.
const skeletonWidths = ['w-52', 'w-40', 'w-60', 'w-44']

const serviceCount = computed(() =>
  accounts.value.reduce((total, account) => total + account.services.length, 0),
)

// A reply for an earlier open (closed and reopened, or another carrier) must not fill this one.
const fetches = createSequence()

watch(open, async (isOpen) => {
  if (!isOpen) fetches.cancel()
  if (!isOpen || !props.provider) return

  const ticket = fetches.next()
  accounts.value = []
  selectedCodes.value = []
  backupCharge.value = '0'
  failed.value = false
  loading.value = true
  try {
    const data = await props.fetchChoices(props.provider.provider)
    if (!fetches.isLatest(ticket)) return
    failed.value = !data
    accounts.value = (data?.accounts ?? [])
      .map((account) => ({
        ...account,
        services: (account.services ?? []).filter((service) => service.service_code),
      }))
      .filter((account) => account.services.length)
  } finally {
    if (fetches.isLatest(ticket)) loading.value = false
  }
})

function toggle(code, checked) {
  selectedCodes.value = checked
    ? [...selectedCodes.value, code]
    : selectedCodes.value.filter((selected) => selected !== code)
}

async function importSelected() {
  if (importing.value) return
  // The carrier's own rows go back with only the account's carrier name added — the server
  // stores all three. Re-deriving a code from a label here is how one gets corrupted.
  const selections = accounts.value.flatMap((account) =>
    account.services
      .filter((service) => selectedCodes.value.includes(service.service_code))
      .map((service) => ({ ...service, carrier: account.carrier })),
  )

  importing.value = true
  try {
    const saved = await props.submit(props.provider.provider, selections, backupCharge.value)
    if (!saved) return

    open.value = false
    toast.success(
      selections.length === 1
        ? __('1 delivery option imported')
        : __('{0} delivery options imported', [selections.length]),
    )
  } finally {
    importing.value = false
  }
}
</script>

<template>
  <Dialog v-model:open="open" :title="provider?.label ? __('Import from {0}', [provider.label]) : __('Import from carrier')">
    <template #default>
      <!-- Shaped like the checkbox rows below — a box and its label — so the dialog does
           not resize under the pointer when the carrier answers. -->
      <div v-if="loading" class="divide-y divide-outline-gray-1" aria-hidden="true">
        <div v-for="row in 4" :key="row" class="flex items-center gap-3 py-2.5">
          <Skeleton class="size-4 shrink-0 rounded-4" />
          <Skeleton class="h-4 rounded-4" :class="skeletonWidths[row % skeletonWidths.length]" />
        </div>
      </div>

      <ErrorMessage
        v-else-if="failed"
        :message="__('These services could not be read from the carrier.')"
      />

      <EmptyState
        v-else-if="!serviceCount"
        compact
        icon="lucide-truck"
        :title="__('No services to import')"
        :description="__('This carrier is not offering any services on the account it is connected with.')"
      />

      <template v-else>
        <p class="text-p-base text-ink-gray-7">
          {{ __('Pick what shoppers should be offered at checkout. Each becomes a delivery option you can rename the price rules on afterwards.') }}
        </p>

        <!-- A carrier lists dozens of services across its accounts, so the list scrolls and
             the price below it — and the Import button under that — stay in reach. -->
        <ScrollArea v-scroll-fade class="mt-4 max-h-96 border-y border-outline-gray-1" viewport-class="pe-3">
          <div v-for="account in accounts" :key="account.carrier" class="pt-3">
            <p class="text-sm text-ink-gray-5">{{ account.description || account.carrier }}</p>
            <div class="mt-1 divide-y divide-outline-gray-1">
              <div
                v-for="service in account.services"
                :key="service.service_code"
                class="flex items-center gap-3 py-2.5"
              >
                <Checkbox
                  :model-value="selectedCodes.includes(service.service_code)"
                  :label="service.service_name"
                  @update:model-value="toggle(service.service_code, $event)"
                />
              </div>
            </div>
          </div>
        </ScrollArea>

        <!-- A carrier that will not quote leaves an option with no price, and an option with
             no price is hidden at checkout rather than shown as free. Set here, once, instead
             of on each imported row afterwards. -->
        <div class="mt-4">
          <FormControl
            v-model="backupCharge"
            type="number"
            :label="__('Fallback price')"
            :description="__('Charged when the carrier gives no quote. Leave at 0 only if you will set a shipping rule on each option.')"
          />
        </div>
      </template>
    </template>

    <template #actions>
      <Button
        class="w-full"
        variant="solid"
        theme="gray"
        :loading="importing"
        :disabled="!selectedCodes.length"
        :label="selectedCodes.length ? __('Import {0}', [selectedCodes.length]) : __('Import')"
        @click="importSelected"
      />
    </template>
  </Dialog>
</template>
