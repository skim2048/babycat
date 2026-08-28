import { createApp } from 'vue'
import App from './App.vue'
import router from './router.js'
import './assets/global.css'
// Apply the theme at app start — the login screen must start with the same theme too.
import './composables/useTheme.js'

createApp(App).use(router).mount('#app')
