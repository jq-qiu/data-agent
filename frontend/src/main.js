/** 创建 Vue 单页应用并加载全局样式；业务交互集中在 App.vue。 */

import { createApp } from "vue";

import App from "./App.vue";
import "./style.css";

createApp(App).mount("#app");
