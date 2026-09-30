<template>
  <div
    v-if="settings.drawerOpen"
    class="drawer-backdrop"
    @click.self="settings.closeDrawer()"
  >
    <aside class="drawer" role="dialog" aria-label="设置">
      <header class="drawer-header">
        <h2>设置</h2>
        <button
          class="icon-button"
          aria-label="关闭"
          @click="settings.closeDrawer()"
        >
          ✕
        </button>
      </header>

      <section class="drawer-section">
        <label class="field">
          <span class="field-label">模型</span>
          <input v-model="modelInput" class="field-input" />
        </label>

        <label class="field">
          <span class="field-label">API 端点</span>
          <input v-model="baseUrlInput" class="field-input" />
        </label>
      </section>

      <section class="drawer-section">
        <span class="field-label">权限确认</span>
        <div class="radio-group">
          <label
            v-for="option in hitlOptions"
            :key="option.value"
            class="radio"
          >
            <input
              type="radio"
              :checked="settings.hitlMode === option.value"
              @change="settings.setHitlMode(option.value)"
            />
            <span>{{ option.label }}</span>
          </label>
        </div>
      </section>

      <footer class="drawer-footer">
        <span class="hint">修改在下次对话时生效</span>
      </footer>
    </aside>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useSettingsStore, type HitlMode } from '@/store/settings'

const settings = useSettingsStore()

const modelInput = ref(settings.modelName)
const baseUrlInput = ref(settings.baseUrl)

// Keep the local buffers in step when the store changes from elsewhere.
watch(() => settings.modelName, (value) => (modelInput.value = value))
watch(() => settings.baseUrl, (value) => (baseUrlInput.value = value))

watch(modelInput, (value) => settings.setModel(value))
watch(baseUrlInput, (value) => settings.setBaseUrl(value))

const hitlOptions: Array<{ value: HitlMode; label: string }> = [
  { value: 'always', label: '每次操作都确认' },
  { value: 'dangerous', label: '仅高危操作确认' },
  { value: 'never', label: '自动放行' },
]
</script>

<style scoped>
.drawer-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.35);
  display: flex;
  justify-content: flex-start;
  z-index: 1000;
}

.drawer {
  width: 360px;
  height: 100%;
  background: #fff;
  display: flex;
  flex-direction: column;
  padding: 16px;
  gap: 20px;
}

.drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.drawer-header h2 {
  font-size: 16px;
  margin: 0;
}

.drawer-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field-label {
  font-size: 13px;
  color: #4e5969;
}

.field-input {
  padding: 8px 10px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  font-size: 13px;
}

.radio-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.radio {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.drawer-footer {
  margin-top: auto;
}

.hint {
  font-size: 12px;
  color: var(--color-text-muted);
}

.icon-button {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 14px;
}
</style>