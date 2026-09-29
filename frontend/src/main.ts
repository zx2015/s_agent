import { createApp } from 'vue'
import { createPinia } from 'pinia'
import MateChat from '@matechat/core'
import 'vue-devui/style.css'
import '@devui-design/icons/icomoon/devui-icon.css'
import 'splitpanes/dist/splitpanes.css'
import 'highlight.js/styles/github.css'
import '@/styles/global.css'

import App from './App.vue'

const app = createApp(App)

app.use(createPinia())
app.use(MateChat)

app.mount('#app')