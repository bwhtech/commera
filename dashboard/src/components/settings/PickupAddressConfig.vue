<script setup>
import { computed, onMounted, reactive, ref, useId } from 'vue'
import { Button, FormControl, FormLabel, SettingsBody, toast } from 'frappe-ui'
import SettingsConfigHeader from './SettingsConfigHeader.vue'
import LocationMap from '../LocationMap.vue'
import SettingsLinkControl from './SettingsLinkControl.vue'
import { useAdminAction } from '../../data/api'

const props = defineProps({
  warehouse: { type: Object, required: true },
  saving: { type: Boolean, default: false },
})

const emit = defineEmits(['back', 'save'])

const COUNTRY_FIELD = { fieldname: 'country', options: 'Country' }
const FIELDNAMES = [
  'address_title',
  'address_line1',
  'address_line2',
  'city',
  'state',
  'pincode',
  'country',
  'phone',
  'custom_store_location',
]

// The Save button sits in the header, outside the form, so `form` is what makes the browser run
// each field's `required` check before anything is sent.
const formId = useId()
const map = ref(null)

const address = props.warehouse.address ?? {}
const values = reactive(
  Object.fromEntries(FIELDNAMES.map((fieldname) => [fieldname, address[fieldname] ?? ''])),
)
values.address_title ||= props.warehouse.warehouse_name
values.country ||= props.warehouse.country

const findLocation = useAdminAction('settings.find_address_location')

// How the pin got where it is, so the line under the map can say so: 'match' for a looked-up
// address, 'device' for this browser's location, 'not-found' when a lookup came back empty.
const pinSource = ref('')
const matches = ref([])
const chosenMatch = ref(null)
const locatingDevice = ref(false)
let lastSearched = ''

const hasPin = computed(() => Boolean(values.custom_store_location))
const canUseDevice = 'geolocation' in navigator

const searchText = computed(() =>
  [values.address_line1, values.address_line2, values.city, values.state, values.pincode, values.country]
    .filter(Boolean)
    .join(', '),
)

const otherMatches = computed(() => matches.value.filter((match) => match !== chosenMatch.value))

async function lookUp(query) {
  const found = await findLocation.submit({ query })
  return findLocation.error ? [] : (found ?? [])
}

// A new address has no pin, so the map opens on its country rather than the whole world.
onMounted(async () => {
  if (hasPin.value || !values.country) return

  const [country] = await lookUp(values.country)
  if (country?.bounds && !hasPin.value) map.value.fitBounds(country.bounds)
})

// A pin the lookup placed follows the address as it is corrected; one the owner placed or dragged,
// or took from their device, is theirs and a later address edit must not move it.
const pinFollowsAddress = computed(() => !hasPin.value || pinSource.value === 'match')

// On blur, never per keystroke: OpenStreetMap's free lookup forbids search-as-you-type and
// allows one request a second. Waits for a city or postal code, or the street matches anywhere.
async function placeFromAddress() {
  if (!pinFollowsAddress.value || (!values.city && !values.pincode)) return
  if (searchText.value === lastSearched) return

  lastSearched = searchText.value
  const found = await lookUp(searchText.value)
  // The owner may have placed the pin by hand while the lookup was out.
  if (!pinFollowsAddress.value) return

  matches.value = found
  if (found.length) chooseMatch(found[0])
  else if (!hasPin.value) pinSource.value = 'not-found'
}

function chooseMatch(match) {
  chosenMatch.value = match
  pinSource.value = 'match'
  map.value.moveTo(match.latitude, match.longitude)
}

function placedByHand() {
  pinSource.value = ''
  matches.value = []
  chosenMatch.value = null
}

function removePin() {
  values.custom_store_location = ''
  placedByHand()
  lastSearched = ''
}

function readDevicePosition() {
  return new Promise((resolve, reject) =>
    navigator.geolocation.getCurrentPosition(resolve, reject, { enableHighAccuracy: true, timeout: 10000 }),
  )
}

async function useCurrentLocation() {
  locatingDevice.value = true
  try {
    const { coords } = await readDevicePosition()
    placedByHand()
    pinSource.value = 'device'
    map.value.moveTo(coords.latitude, coords.longitude)
  } catch (error) {
    // Code 1 is the owner (or the browser) refusing; anything else is the device not answering.
    toast.error(
      error?.code === 1
        ? 'Location access is blocked. Allow it in your browser, or click the map.'
        : 'Your location could not be found. Click the map to place the pin.',
    )
  } finally {
    locatingDevice.value = false
  }
}
</script>

<template>
  <SettingsConfigHeader
    :title="warehouse.warehouse_name"
    description="Pickup address"
    @back="emit('back')"
  >
    <template #actions>
      <Button
        label="Save"
        type="submit"
        :form="formId"
        variant="solid"
        theme="gray"
        :loading="saving"
        :disabled="!values.country"
      />
    </template>
  </SettingsConfigHeader>

  <SettingsBody v-scroll-fade>
    <form :id="formId" class="flex flex-col gap-4 pt-4" @submit.prevent="emit('save', { ...values })">
      <FormControl
        v-model="values.address_title"
        label="Name at checkout"
        required
        description="What shoppers read when they pick where to collect."
      />

      <!-- focusout bubbles where blur does not, so one listener hears every address field settle. -->
      <div class="flex flex-col gap-4" @focusout="placeFromAddress">
        <FormControl v-model="values.address_line1" label="Address line 1" required />
        <FormControl v-model="values.address_line2" label="Address line 2" />

        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FormControl v-model="values.city" label="City" required />
          <FormControl v-model="values.state" label="State" />
          <FormControl v-model="values.pincode" label="Postal code" />
          <SettingsLinkControl
            v-model="values.country"
            :field="COUNTRY_FIELD"
            options-path="settings.get_link_options"
            label="Country"
            required
            class="!w-full"
          />
        </div>
      </div>

      <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <FormControl v-model="values.phone" label="Phone" type="tel" />
      </div>

      <div class="flex flex-col gap-2">
        <div class="flex items-center justify-between gap-2">
          <FormLabel label="Location on the map" />
          <Button
            v-if="canUseDevice"
            label="Use my current location"
            icon-left="lucide-locate-fixed"
            :loading="locatingDevice"
            @click="useCurrentLocation"
          />
        </div>

        <LocationMap
          ref="map"
          v-model="values.custom_store_location"
          empty-hint="No pin yet — click the map to place one"
          @place-by-hand="placedByHand"
        />

        <div class="flex items-start justify-between gap-3">
          <p class="min-w-0 text-sm text-ink-gray-5">
            <template v-if="findLocation.loading && !hasPin">Looking up the address…</template>
            <template v-else-if="pinSource === 'match'">
              Pinned near <span class="text-ink-gray-7">{{ chosenMatch.label }}</span>. Drag the pin if it
              is off.
            </template>
            <template v-else-if="pinSource === 'device'">
              Pinned at your current location. Drag the pin if it is off.
            </template>
            <template v-else-if="pinSource === 'not-found' && !hasPin">
              That address is not on the map. Click the map to place the pin.
            </template>
            <template v-else-if="hasPin">Drag the pin to adjust it.</template>
            <template v-else>Fill in the address and the pin is placed for you.</template>
          </p>
          <Button v-if="hasPin" label="Remove pin" variant="ghost" @click="removePin" />
        </div>

        <!-- The best match is only a guess when a street name repeats across a city, so the rest
             stay one click away rather than behind another search. -->
        <div v-if="pinSource === 'match' && otherMatches.length" class="flex flex-col gap-1">
          <p class="text-sm text-ink-gray-5">Not the right place?</p>
          <Button
            v-for="match in otherMatches"
            :key="`${match.latitude},${match.longitude}`"
            variant="ghost"
            icon-left="lucide-map-pin"
            class="h-auto !justify-start py-1.5"
            :label="match.label"
            @click="chooseMatch(match)"
          />
        </div>
      </div>
    </form>
  </SettingsBody>
</template>
