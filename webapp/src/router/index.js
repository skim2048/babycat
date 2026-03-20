import { createRouter, createWebHistory } from 'vue-router'
import HomePage from '@/views/HomePage/HomePage.vue'
import SchedulePage from '@/views/SchedulePage.vue'
import AlarmPage from '@/views/AlarmPage.vue'
import SettingsPage from '@/views/SettingsPage.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/home' },
    { path: '/home', component: HomePage },
    { path: '/schedule', component: SchedulePage },
    { path: '/alarm', component: AlarmPage },
    { path: '/settings', component: SettingsPage },
  ]
})

export default router
