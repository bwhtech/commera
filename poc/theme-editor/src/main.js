import { createApp } from 'vue'
import { FrappeUI } from 'frappe-ui'
import { createRouter, createWebHistory } from 'vue-router'
import './style.css'
import App from './App.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: () => import('./pages/Themes.vue') },
    { path: '/pages', component: () => import('./pages/Pages.vue') },
    { path: '/storefront', redirect: '/storefront/themes' },
    { path: '/storefront/themes', component: () => import('./storefront/Themes.vue') },
    { path: '/storefront/themes/:theme', component: () => import('./storefront/BuilderTheme.vue') },
    { path: '/storefront/pages', component: () => import('./storefront/Pages.vue') },
    { path: '/storefront/pages/:page', component: () => import('./storefront/PageEditor.vue') },
    {
      path: '/storefront/navigation',
      component: () => import('./storefront/Placeholder.vue'),
      props: { title: 'Navigation', text: 'Menus for your header and footer. Every theme uses them.' },
    },
    {
      path: '/storefront/preferences',
      component: () => import('./storefront/Placeholder.vue'),
      props: { title: 'Preferences', text: 'Store title, search engine listing, social sharing image, password protection.' },
    },
    { path: '/variations', component: () => import('./variations/Variations.vue') },
    { path: '/variations/a', component: () => import('./variations/VariantA.vue') },
    { path: '/variations/b', component: () => import('./variations/VariantB.vue') },
    { path: '/variations/c', component: () => import('./variations/VariantC.vue') },
    { path: '/themes/:theme/customize', component: () => import('./pages/ThemeEditor.vue') },
  ],
})

createApp(App).use(router).use(FrappeUI).mount('#app')
