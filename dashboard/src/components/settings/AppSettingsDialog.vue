<script setup>
import { watch } from 'vue'
import {
  SettingsBody,
  SettingsContent,
  SettingsDialog,
  SettingsHeader,
  SettingsNavGroup,
  SettingsNavItem,
  SettingsPanel,
  SettingsSidebar,
} from 'frappe-ui'
import AdvancedSettings from './AdvancedSettings.vue'
import AppearancePicker from './AppearancePicker.vue'
import AppsSettings from './AppsSettings.vue'
import CashOnDeliverySettings from './CashOnDeliverySettings.vue'
import DeliveryOptionsPanel from './DeliveryOptionsPanel.vue'
import ShippingRulesPanel from './ShippingRulesPanel.vue'
import GeneralSettings from './GeneralSettings.vue'
import IntegrationsPanel from './IntegrationsPanel.vue'
import LocationsSettings from './LocationsSettings.vue'
import { paymentIntegrations, shippingIntegrations } from '../../data/integrations'
import { settings } from '../../ia/settings'

// The counts beside the sidebar entries are the server's answer, not a local tally, so
// they cannot claim a provider is live when the site says otherwise.
const connectedCount = paymentIntegrations.connectedCount
const shippingConnected = shippingIntegrations.connectedCount

// Both registries load when the dialog opens, not when their tab is first shown: the
// counts sit in the sidebar from the start, and an unread registry counts zero, which
// reads as "nothing is connected" rather than "not looked yet".
watch(
  () => settings.open,
  (isOpen) => {
    if (!isOpen) return
    paymentIntegrations.loadOnce()
    shippingIntegrations.loadOnce()
  },
  { immediate: true },
)
</script>

<template>
  <SettingsDialog v-model:open="settings.open" v-model:tab="settings.tab" :unmount-on-hide="false">
    <template #title>Commera settings</template>

    <SettingsSidebar>
      <SettingsNavGroup>
        <SettingsNavItem value="general">
          <template #prefix><span class="lucide-store size-4" aria-hidden="true" /></template>
          General
        </SettingsNavItem>
        <SettingsNavItem value="locations">
          <template #prefix><span class="lucide-map-pin size-4" aria-hidden="true" /></template>
          Locations
        </SettingsNavItem>
        <SettingsNavItem value="appearance">
          <template #prefix><span class="lucide-sun-moon size-4" aria-hidden="true" /></template>
          Appearance
        </SettingsNavItem>
      </SettingsNavGroup>

      <SettingsNavGroup label="Selling">
        <SettingsNavItem value="payments">
          <template #prefix><span class="lucide-credit-card size-4" aria-hidden="true" /></template>
          Payments
          <template #suffix>
            <span class="text-sm text-ink-gray-5 tabular-nums">{{ connectedCount }}</span>
          </template>
        </SettingsNavItem>
        <SettingsNavItem value="shipping">
          <template #prefix><span class="lucide-truck size-4" aria-hidden="true" /></template>
          Shipping
          <template #suffix>
            <span class="text-sm text-ink-gray-5 tabular-nums">{{ shippingConnected }}</span>
          </template>
        </SettingsNavItem>
      </SettingsNavGroup>

      <SettingsNavGroup label="Connections">
        <SettingsNavItem value="apps">
          <template #prefix><span class="lucide-chart-line size-4" aria-hidden="true" /></template>
          Analytics
        </SettingsNavItem>
        <SettingsNavItem value="advanced">
          <template #prefix><span class="lucide-sliders-horizontal size-4" aria-hidden="true" /></template>
          Advanced
        </SettingsNavItem>
      </SettingsNavGroup>
    </SettingsSidebar>

    <!-- min-w-0 on the content column and every panel: frappe-ui gives them `flex-1`
         with no min-width, so a flex item's `auto` floor keeps the column at its
         min-content width (530px here) and the surplus is clipped by the dialog's
         own overflow-hidden. Below roughly 780px of viewport that cut the right-hand
         controls — Configure, Save, the theme cards — clean off the edge. -->
    <SettingsContent class="min-w-0">
      <SettingsPanel value="general" class="min-w-0">
        <GeneralSettings :active="settings.open && settings.tab === 'general'" />
      </SettingsPanel>

      <SettingsPanel value="locations" class="min-w-0">
        <LocationsSettings :active="settings.open && settings.tab === 'locations'" />
      </SettingsPanel>

      <!-- Light and dark are a property of this browser, not of the store, so
           Appearance sits with the other personal settings and nowhere near
           the storefront theme. -->
      <SettingsPanel value="appearance" class="min-w-0">
        <!-- The default slot rather than the title prop: the subtitle told the owner nothing the
             three cards do not, but its height is kept so this tab's header sits level with the
             others in the dialog. -->
        <SettingsHeader>
          <div class="flex min-w-0 flex-col gap-1">
            <h2 class="text-lg font-semibold text-ink-gray-8">Appearance</h2>
            <p class="text-base" aria-hidden="true">&nbsp;</p>
          </div>
        </SettingsHeader>
        <SettingsBody>
          <AppearancePicker />
        </SettingsBody>
      </SettingsPanel>

      <!-- Payments: several gateways can run side by side, each with its own
           keys and environment. Only the checkout default is exclusive. -->
      <SettingsPanel value="payments" class="min-w-0">
        <!-- Same two-step story as Shipping: the gateways a store connects, then the one
             method it settles itself. The tail padding goes for the same reason. -->
        <div class="flex shrink-0 flex-col [&_[data-slot=scroll-area-viewport]]:pb-0">
          <IntegrationsPanel
            :store="paymentIntegrations"
            :active="settings.tab === 'payments'"
            title="Payments"
            description="Turn on as many providers as you like. Each keeps its own keys."
          />
        </div>
        <CashOnDeliverySettings :active="settings.open && settings.tab === 'payments'" />
      </SettingsPanel>

      <!-- Shipping reads as one story in two steps: connect a carrier, then say what
           shoppers may pick from it. The carrier list is short and fixed, so it takes
           only the height it needs and the options below get the rest of the scroll. -->
      <SettingsPanel value="shipping" class="min-w-0">
        <!-- The carrier list is the first of two sections rather than a whole panel, so its
             body drops the 4rem of tail padding a panel ends on; the section below supplies
             its own top spacing. Reached through frappe-ui's own data-slot, which is the
             supported hook — IntegrationsPanel itself stays generic and untouched. -->
        <div class="flex shrink-0 flex-col [&_[data-slot=scroll-area-viewport]]:pb-0">
          <IntegrationsPanel
            :store="shippingIntegrations"
            :active="settings.tab === 'shipping'"
            title="Shipping"
            description="Carriers this store books with. Each quotes its own rates at checkout."
          />
        </div>
        <!-- Now a middle section too, so it drops its tail padding the same way. -->
        <div class="flex shrink-0 flex-col [&_[data-slot=scroll-area-viewport]]:pb-0">
          <DeliveryOptionsPanel :active="settings.open && settings.tab === 'shipping'" />
        </div>
        <ShippingRulesPanel :active="settings.open && settings.tab === 'shipping'" />
      </SettingsPanel>

      <SettingsPanel value="apps" class="min-w-0">
        <AppsSettings :active="settings.open && settings.tab === 'apps'" />
      </SettingsPanel>

      <SettingsPanel value="advanced" class="min-w-0">
        <AdvancedSettings :active="settings.open && settings.tab === 'advanced'" />
      </SettingsPanel>
    </SettingsContent>
  </SettingsDialog>
</template>
