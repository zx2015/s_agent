<template>
  <div class="three-column">
    <Splitpanes class="default-theme" @resize="onResize" @resized="onResize">
      <Pane
        v-if="!leftCollapsed"
        class="pane-left"
        :size="leftSize"
        min-size="14"
        max-size="34"
      >
        <div class="pane-inner">
          <SidebarLeft />
          <button
            class="collapse-toggle toggle-left toggle-left-open"
            aria-label="折叠左侧栏"
            title="折叠左侧栏"
            @click="toggleLeftCollapse"
          >
            ◂
          </button>
        </div>
      </Pane>

      <Pane class="pane-middle" :size="middleSize" min-size="30">
        <SidebarMiddle />
      </Pane>

      <Pane
        v-if="!rightCollapsed"
        class="pane-right"
        :size="rightSize"
        min-size="18"
        max-size="42"
      >
        <div class="pane-inner">
          <button
            class="collapse-toggle toggle-right toggle-right-open"
            aria-label="折叠结果区"
            title="折叠结果区"
            @click="toggleRightCollapse"
          >
            ▸
          </button>
          <SidebarRight />
        </div>
      </Pane>
    </Splitpanes>

    <!-- Floating toggle buttons when respective sidebars are collapsed -->
    <button
      v-if="leftCollapsed"
      class="collapse-toggle toggle-left toggle-left-closed"
      aria-label="展开左侧栏"
      title="展开左侧栏"
      @click="toggleLeftCollapse"
    >
      ▸
    </button>

    <button
      v-if="rightCollapsed"
      class="collapse-toggle toggle-right toggle-right-closed"
      aria-label="展开结果区"
      title="展开结果区"
      @click="toggleRightCollapse"
    >
      ◂
    </button>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { Pane, Splitpanes } from 'splitpanes'
import SidebarLeft from '@/components/sidebar/SidebarLeft.vue'
import SidebarMiddle from '@/components/chat/SidebarMiddle.vue'
import SidebarRight from '@/components/artifacts/SidebarRight.vue'
import { useSessionStore } from '@/store/session'

const session = useSessionStore()

const leftCollapsed = ref(false)
const rightCollapsed = ref(true) // collapsed until there is something to show

const leftSize = ref(20)
const middleSize = ref(80)
const rightSize = ref(30)

function toggleLeftCollapse(): void {
  if (leftCollapsed.value) {
    leftCollapsed.value = false
    middleSize.value = Math.max(30, 100 - leftSize.value - (rightCollapsed.value ? 0 : rightSize.value))
  } else {
    leftCollapsed.value = true
    middleSize.value = 100 - (rightCollapsed.value ? 0 : rightSize.value)
  }
}

function toggleRightCollapse(): void {
  if (rightCollapsed.value) {
    rightCollapsed.value = false
    middleSize.value = Math.max(30, 100 - (leftCollapsed.value ? 0 : leftSize.value) - rightSize.value)
  } else {
    rightCollapsed.value = true
    middleSize.value = 100 - (leftCollapsed.value ? 0 : leftSize.value)
  }
}

// Spec §1.2: the result pane opens itself when an artifact appears, so the
// user does not have to guess that there is something to look at.
watch(
  () => session.artifacts.length,
  (count, previous) => {
    if (count > (previous ?? 0) && rightCollapsed.value) {
      toggleRightCollapse()
    }
  },
)

/**
 * Track the pane sizes so a collapse/expand cycle can restore them.
 *
 * The payload always carries the full pane list, so which visible pane
 * maps to which stored size depends on how many panes are currently
 * mounted — that is what the branch below unpacks.
 *
 * @param payload - The resize event carrying the current pane sizes.
 */
function onResize(payload: any): void {
  const panes = Array.isArray(payload) ? payload : (payload?.panes || [])
  const sizes = panes.map((pane: any) => pane.size)
  if (sizes.length === 0) return

  if (!leftCollapsed.value && !rightCollapsed.value && sizes.length >= 3) {
    ;[leftSize.value, middleSize.value, rightSize.value] = sizes
  } else if (leftCollapsed.value && rightCollapsed.value && sizes.length >= 1) {
    middleSize.value = sizes[0]
  } else if (leftCollapsed.value && sizes.length >= 2) {
    middleSize.value = sizes[0]
    rightSize.value = sizes[1]
  } else if (sizes.length >= 2) {
    leftSize.value = sizes[0]
    middleSize.value = sizes[1]
  }
}
</script>

<style scoped>
.three-column {
  position: relative;
  height: 100%;
  width: 100%;
}

:deep(.splitpanes__pane.pane-left),
:deep(.splitpanes__pane.pane-right) {
  overflow: visible !important;
  position: relative;
}

.pane-inner {
  position: relative;
  width: 100%;
  height: 100%;
}

.collapse-toggle {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  width: 16px;
  height: 40px;
  background: var(--color-bg-base);
  border: 1px solid var(--color-border);
  cursor: pointer;
  font-size: 10px;
  z-index: 10;
  padding: 0;
  color: var(--color-text-muted);
  display: flex;
  align-items: center;
  justify-content: center;
  user-select: none;
  transition: background-color 0.15s, color 0.15s;
}

.collapse-toggle:hover {
  background: var(--color-bg-subtle);
  color: var(--color-text);
}

.toggle-left-open {
  right: -16px;
  border-left: none;
  border-radius: 0 4px 4px 0;
}

.toggle-left-closed {
  left: 0;
  border-left: none;
  border-radius: 0 4px 4px 0;
}

.toggle-right-open {
  left: -16px;
  border-right: none;
  border-radius: 4px 0 0 4px;
}

.toggle-right-closed {
  right: 0;
  border-right: none;
  border-radius: 4px 0 0 4px;
}
</style>