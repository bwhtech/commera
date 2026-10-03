<script setup>
import { watch } from 'vue'
import {
  SettingsBody,
  SettingsContent,
  SettingsDialog,
  SettingsNavGroup,
  SettingsNavItem,
  SettingsPanel,
  SettingsSidebar,
} from 'frappe-ui'
import AdvancedSettings from './AdvancedSettings.vue'
import AppearancePicker from './AppearancePicker.vue'
import AppsSettings from './AppsSettings.vue'
import CashOnDeliverySettings from './CashOnDeliverySettings.vue'
import CheckoutSettings from './CheckoutSettings.vue'
import DeliveryOptionsPanel from './DeliveryOptionsPanel.vue'
import EmailSettings from './EmailSettings.vue'
import GeneralSettings from './GeneralSettings.vue'
import IntegrationTabPanel from './IntegrationTabPanel.vue'
import LocationsSettings from './LocationsSettings.vue'
import SettingsPanelHeader from './SettingsPanelHeader.vue'
import { paymentIntegrations, shippingIntegrations } from '../../data/integrations'
import { pickupLocations } from '../../data/pickupLocations'
import { settings } from '../../ia/settings'

// The counts beside the sidebar entries are the server's answer, not a local tally, so
// they cannot claim a provider is live when the site says otherwise.
const connectedCount = paymentIntegrations.connectedCount
const shippingConnected = shippingIntegrations.connectedCount

// Both load when the dialog opens, not when their tab is shown: an unread registry counts
// zero, which reads as "nothing is connected".
watch(
  () => settings.open,
  (isOpen) => {
    if (!isOpen) return
    paymentIntegrations.loadOnce()
    shippingIntegrations.loadOnce()
    pickupLocations.loadOnce()
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
        <SettingsNavItem value="appearance">
          <template #prefix><span class="lucide-sun-moon size-4" aria-hidden="true" /></template>
          Appearance
        </SettingsNavItem>
        <SettingsNavItem value="emails">
          <template #prefix><span class="lucide-mail size-4" aria-hidden="true" /></template>
          Emails
        </SettingsNavItem>
      </SettingsNavGroup>

      <SettingsNavGroup label="Checkout">
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
        <SettingsNavItem value="locations">
          <template #prefix><span class="lucide-map-pin size-4" aria-hidden="true" /></template>
          Pickup locations
          <!-- Nothing while pickup is off: a count there would suggest shoppers can collect today. -->
          <template v-if="pickupLocations.pickupEnabled.value" #suffix>
            <span class="text-sm text-ink-gray-5 tabular-nums">{{ pickupLocations.activeCount.value }}</span>
          </template>
        </SettingsNavItem>
        <SettingsNavItem value="checkout">
          <template #prefix><span class="lucide-shopping-cart size-4" aria-hidden="true" /></template>
          General
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

    <!-- min-w-0 on the column and every panel: frappe-ui gives them `flex-1` with no
         min-width, so below ~780px the right-hand controls are clipped clean off. -->
    <SettingsContent class="min-w-0">
      <SettingsPanel value="general" class="min-w-0">
        <GeneralSettings :active="settings.open && settings.tab === 'general'" />
      </SettingsPanel>

      <SettingsPanel value="emails" class="min-w-0">
        <EmailSettings :active="settings.open && settings.tab === 'emails'" />
      </SettingsPanel>

      <SettingsPanel value="locations" class="min-w-0">
        <LocationsSettings :active="settings.open && settings.tab === 'locations'" />
      </SettingsPanel>

      <SettingsPanel value="checkout" class="min-w-0">
        <CheckoutSettings :active="settings.open && settings.tab === 'checkout'" />
      </SettingsPanel>

      <SettingsPanel value="appearance" class="min-w-0">
        <!-- The blank line keeps this tab's header level with the others. -->
        <SettingsPanelHeader>
          <div class="flex min-w-0 flex-col gap-1">
            <h2 class="text-lg font-semibold text-ink-gray-8">Appearance</h2>
            <p class="text-base" aria-hidden="true">&nbsp;</p>
          </div>
        </SettingsPanelHeader>
        <SettingsBody v-scroll-fade>
          <AppearancePicker />
        </SettingsBody>
      </SettingsPanel>

      <SettingsPanel value="payments" class="min-w-0">
        <IntegrationTabPanel
          :store="paymentIntegrations"
          :active="settings.tab === 'payments'"
          title="Payments"
          description="Turn on as many providers as you like. Each keeps its own keys."
        >
          <CashOnDeliverySettings :active="settings.open && settings.tab === 'payments'" />
        </IntegrationTabPanel>
      </SettingsPanel>

      <SettingsPanel value="shipping" class="min-w-0">
        <IntegrationTabPanel
          v-slot="{ takeover, setTakeover }"
          :store="shippingIntegrations"
          :active="settings.tab === 'shipping'"
          title="Shipping"
          description="Carriers this store books with. Each quotes its own rates at checkout."
        >
          <DeliveryOptionsPanel
            :configuring="takeover"
            :active="settings.open && settings.tab === 'shipping'"
            @update:configuring="setTakeover"
          />
        </IntegrationTabPanel>
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
