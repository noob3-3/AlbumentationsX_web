<template>
  <el-dialog
    v-model="visible"
    title="软件授权"
    width="520px"
    destroy-on-close
  >
    <el-alert
      :title="license.message || '未激活'"
      :type="license.valid ? 'success' : 'warning'"
      :closable="false"
      show-icon
      style="margin-bottom: 16px"
    />

    <el-form label-width="88px">
      <el-form-item label="机器码">
        <el-input :model-value="license.machineCode" readonly>
          <template #append>
            <el-button @click="copyMachine">复制</el-button>
          </template>
        </el-input>
      </el-form-item>
      <el-form-item v-if="!license.valid" label="激活码">
        <el-input
          v-model="code"
          type="textarea"
          :rows="3"
          placeholder="请输入厂商签发的激活码"
        />
      </el-form-item>
    </el-form>

    <div v-if="hwText" class="hw-line">本机：{{ hwText }}</div>

    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
      <el-button
        v-if="!license.valid"
        type="primary"
        :loading="submitting"
        :disabled="!code.trim()"
        @click="submit"
      >
        激活
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { ElMessage } from 'element-plus'
import { useLicenseStore } from '@/stores/license'

const licenseStore = useLicenseStore()
const { dialogVisible: visible } = storeToRefs(licenseStore)
const license = licenseStore

const code = ref('')
const submitting = ref(false)

const hwText = computed(() => {
  const hw = license.hardware || {}
  return [hw.host, hw.mac, hw.disk].filter(Boolean).join(' / ')
})

async function copyMachine() {
  const text = license.machineCode
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('机器码已复制')
  } catch {
    ElMessage.error('复制失败，请手动选择机器码')
  }
}

async function submit() {
  submitting.value = true
  try {
    const res = await licenseStore.activate(code.value)
    if (res.valid) {
      ElMessage.success(res.message)
      code.value = ''
      visible.value = false
    }
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.hw-line {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}
</style>
