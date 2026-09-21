import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { licenseApi } from '@/api'

export const useLicenseStore = defineStore('license', () => {
  const valid = ref(false)
  const message = ref('未激活')
  const machineCode = ref('')
  const expireOn = ref(null)
  const projectName = ref('')
  const hardware = ref({ mac: '', disk: '', guid: '', host: '' })
  const loading = ref(false)
  const dialogVisible = ref(false)

  const licensed = computed(() => valid.value)
  const statusType = computed(() => (valid.value ? 'success' : 'danger'))

  async function fetchLicense() {
    loading.value = true
    try {
      const res = await licenseApi.get()
      valid.value = !!res.valid
      message.value = res.message || '未激活'
      machineCode.value = res.machine_code || ''
      expireOn.value = res.expire_on || null
      projectName.value = res.project_name || ''
      hardware.value = res.hardware || { mac: '', disk: '', guid: '', host: '' }
      return res
    } finally {
      loading.value = false
    }
  }

  async function activate(activationCode) {
    const res = await licenseApi.activate(activationCode)
    valid.value = !!res.valid
    message.value = res.message || '未激活'
    machineCode.value = res.machine_code || machineCode.value
    expireOn.value = res.expire_on || null
    hardware.value = res.hardware || hardware.value
    return res
  }

  function openDialog() {
    dialogVisible.value = true
  }

  return {
    valid,
    licensed,
    message,
    machineCode,
    expireOn,
    projectName,
    hardware,
    loading,
    dialogVisible,
    statusType,
    fetchLicense,
    activate,
    openDialog,
  }
})
