<template>
  <div class="three-column">
    <Splitpanes class="default-theme" @resize="onResize">
      <Pane v-if="!leftCollapsed" :size="leftSize" min-size="14" max-size="34">
        <SidebarLeft />
      </Pane>

      <Pane :size="middleSize" min-size="30">
        <SidebarMiddle />
      </Pane>

      <Pane
        v-if="!rightCollapsed"
        :size="rightSize"
        min-size="18"
        max-size="42"
      >
        <SidebarRight />
      </Pane>
    </Splitpanes>

    <button
      class="collapse-toggle toggle-left"
      :style="{ left: leftCollapsed ? '0' : `${leftSize}%` }"
      :aria-label="leftCollapsed ? '展开左侧栏' : '折叠左侧栏'"
      @click="leftCollapsed = !leftCollapsed"
    >
      {{ leftCollapsed ? '▸' : '◂' }}
    </button>

    <button
      class="collapse-toggle toggle-right"
      :style="{ right: rightCollapsed ? '0' : `${rightSize}%` }"
      :aria-label="rightCollapsed ? '展开结果区' : '折叠结果区'"
      @click="rightCollapsed = !rightCollapsed"
    >
      {{ rightCollapsed ? '◂' : '▸' }}
    </button>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { Pane, Splitpanes } from 'splitpanes'
import type { SplitpanesResizePayload } from 'splitpanes'
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

// Spec §1.2: the result pane opens itself when an artifact appears, so the
// user does not have to guess that there is something to look at.
watch(
  () => session.artifacts.length,
  (count, previous) => {
    if (count > (previous ?? 0)) {
      rightCollapsed.value = false
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
function onResize(payload: SplitpanesResizePayload): void {
  const sizes = payload.panes.map((pane) => pane.size)

  if (!leftCollapsed.value && !rightCollapsed.value) {
    ;[leftSize.value, middleSize.value, rightSize.value] = sizes
  } else if (leftCollapsed.value && rightCollapsed.value) {
    middleSize.value = sizes[0]
  } else if (leftCollapsed.value) {
    middleSize.value = sizes[0]
    rightSize.value = sizes[1]
  } else {
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

.collapse-toggle {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  width: 16px;
  height: 40px;
  background: #fff;
  border: 1px solid var(--color-border);
  cursor: pointer;
  font-size: 10px;
  z-index: 10;
  padding: 0;
  color: #86909c;
}

.toggle-left {
  border-left: none;
  border-radius: 0 4px 4px 0;
}

.toggle-right {
  border-right: none;
  border-radius: 4px 0 0 4px;
}
</style>