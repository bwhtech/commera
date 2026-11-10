<script setup>
/**
 * One pin on an OpenStreetMap map, held as the GeoJSON a Frappe Geolocation field stores — so a
 * pin dropped here is the same pin Desk draws on the Address form, and the other way round.
 */
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import markerIcon from 'leaflet/dist/images/marker-icon.png'
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png'
import markerShadow from 'leaflet/dist/images/marker-shadow.png'
import { __ } from '../data/translation'

const props = defineProps({
  modelValue: { type: String, default: '' },
  // Shown over the map while there is no pin, so a blank map says what to do with it.
  emptyHint: { type: String, default: '' },
})

const emit = defineEmits(['update:modelValue', 'place-by-hand'])

const WORLD_ZOOM = 2
const STREET_ZOOM = 16

// Leaflet finds its default marker by reading a CSS url at runtime, which Vite has already
// rewritten — so the default icon renders as a broken image unless it is handed over directly.
const icon = L.icon({
  iconUrl: markerIcon,
  iconRetinaUrl: markerIcon2x,
  shadowUrl: markerShadow,
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  shadowSize: [41, 41],
})

const container = ref(null)
let map = null
let marker = null
let resizeObserver = null

function readPoint(geojson) {
  try {
    const feature = JSON.parse(geojson).features?.find((item) => item.geometry?.type === 'Point')
    const [longitude, latitude] = feature?.geometry?.coordinates ?? []
    return Number.isFinite(latitude) && Number.isFinite(longitude) ? [latitude, longitude] : null
  } catch {
    return null
  }
}

function formatGeojson([latitude, longitude]) {
  return JSON.stringify({
    type: 'FeatureCollection',
    features: [
      { type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: [longitude, latitude] } },
    ],
  })
}

function placeMarker(point) {
  if (marker) {
    marker.setLatLng(point)
    return
  }

  marker = L.marker(point, { icon, draggable: true }).addTo(map)
  marker.on('dragend', () => placeByHand(marker.getLatLng()))
}

function savePin({ lat, lng }) {
  placeMarker([lat, lng])
  emit('update:modelValue', formatGeojson([lat, lng]))
}

// Told apart from a pin placed in code, so a caller can stop describing a pin the owner has since
// put somewhere else by hand.
function placeByHand(latlng) {
  savePin(latlng)
  emit('place-by-hand')
}

// Moves the map and the pin together, for a looked-up address or the device's location.
function moveTo(latitude, longitude) {
  map.setView([latitude, longitude], STREET_ZOOM)
  savePin({ lat: latitude, lng: longitude })
}

// Frames an area without pinning anything — a country, before the owner has said where in it.
function fitBounds(bounds) {
  map.fitBounds(bounds)
}

defineExpose({ moveTo, fitBounds })

onMounted(() => {
  const point = readPoint(props.modelValue)
  map = L.map(container.value).setView(point ?? [20, 0], point ? STREET_ZOOM : WORLD_ZOOM)
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: `&copy; ${__('OpenStreetMap contributors')}`,
  }).addTo(map)

  if (point) placeMarker(point)
  map.on('click', (event) => placeByHand(event.latlng))

  // A map measured while its dialog is still animating open draws as a grey strip; it has to be
  // told once the box has its real size.
  resizeObserver = new ResizeObserver(() => map?.invalidateSize())
  resizeObserver.observe(container.value)
})

watch(
  () => props.modelValue,
  (geojson) => {
    const point = readPoint(geojson)
    if (!map) return
    if (!point) {
      marker?.remove()
      marker = null
      return
    }
    const current = marker?.getLatLng()
    if (current?.lat !== point[0] || current?.lng !== point[1]) placeMarker(point)
  },
)

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  map?.remove()
  map = null
  marker = null
})
</script>

<template>
  <div class="relative">
    <div ref="container" class="isolate h-64 w-full overflow-hidden rounded border border-outline-gray-2" />
    <!-- A sibling of the map rather than a child: the container's `isolate` keeps Leaflet's own
         400-1000 z-indexes inside it, so a plain z-10 is enough to sit on top. It ignores the
         pointer, because clicking straight through it is how the pin gets placed. -->
    <div
      v-if="!modelValue && emptyHint"
      class="pointer-events-none absolute inset-x-0 top-3 z-10 flex justify-center px-3"
    >
      <!-- Palette colours, not theme tokens, on purpose: the pill sits on map tiles that stay light
           in both themes, and every token flips in dark mode (surface-gray-7 turns light grey under
           white text). Frappe-ui defines the raw gray scale once, so it does not flip. -->
      <p class="rounded-full bg-gray-900 px-3 py-1.5 text-sm text-white shadow">{{ emptyHint }}</p>
    </div>
  </div>
</template>
