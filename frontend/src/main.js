import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import { SplashScreen } from '@capacitor/splash-screen'

const app = createApp(App)
app.use(router)
app.mount('#app')

SplashScreen.hide()