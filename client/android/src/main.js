import { createApp } from 'vue'
import App from './App.vue'
import router from './router.js'
import './assets/global.css'
// 앱 시작 시점에 테마를 적용한다 — 로그인 화면도 같은 테마로 시작해야 한다.
import './composables/useTheme.js'

createApp(App).use(router).mount('#app')
