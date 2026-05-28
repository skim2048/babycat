import { createApp } from 'vue'
import App from './App.vue'
import { connect } from './state.js'
import './assets/global.css'

connect()
createApp(App).mount('#app')
