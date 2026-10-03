import { createApp } from 'vue'
import { FrappeUI } from 'frappe-ui'
import { createRouter, createWebHistory } from 'vue-router'
import './style.css'
import App from './App.vue'
import { loadRegistry } from './ia/extensions.js'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: () => import('./pages/Home.vue') },
    { path: '/orders/:id', component: () => import('./pages/OrderDetail.vue') },
    { path: '/apps/:app/:page/:path(.*)*', component: () => import('./pages/ExtensionPage.vue') },
  ],
})

// The registry must be in place before the first render so the sidebar and
// slots see extensions; in Commera it rides the boot payload instead.
await loadRegistry()
createApp(App).use(router).use(FrappeUI).mount('#app')
