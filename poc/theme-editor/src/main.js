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
    { path: '/variations', component: () => import('./variations/Variations.vue') },
    { path: '/variations/a', component: () => import('./variations/VariantA.vue') },
    { path: '/variations/b', component: () => import('./variations/VariantB.vue') },
    { path: '/variations/c', component: () => import('./variations/VariantC.vue') },
    { path: '/themes/:theme/customize', component: () => import('./pages/ThemeEditor.vue') },
  ],
})

createApp(App).use(router).use(FrappeUI).mount('#app')
