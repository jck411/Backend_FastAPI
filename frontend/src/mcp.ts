import { mount } from 'svelte'
import McpStandalone from './McpStandalone.svelte'

const app = mount(McpStandalone, {
    target: document.getElementById('app')!,
})

export default app
