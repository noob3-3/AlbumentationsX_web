import { defineStore } from 'pinia'
import { ref } from 'vue'
import { trainingApi } from '@/api'
import { ElMessage } from 'element-plus'

export const useTrainingStore = defineStore('training', () => {
  const jobs = ref([])
  const currentJob = ref(null)
  const models = ref([])
  const loading = ref(false)

  // Active WebSocket connections: { jobId: WebSocket }
  const wsConnections = ref({})

  async function fetchJobs(params = {}) {
    loading.value = true
    try {
      const res = await trainingApi.listJobs(params)
      jobs.value = res.items
    } finally {
      loading.value = false
    }
  }

  async function createJob(data) {
    const job = await trainingApi.createJob(data)
    jobs.value.unshift(job)
    ElMessage.success('训练任务已创建并启动')
    return job
  }

  async function fetchJob(id) {
    currentJob.value = await trainingApi.getJob(id)
    return currentJob.value
  }

  async function cancelJob(id) {
    await trainingApi.cancelJob(id)
    const job = jobs.value.find((j) => j.id === id)
    if (job) job.status = 'cancelled'
    ElMessage.warning('任务取消请求已发送')
  }

  async function stopJob(id) {
    await trainingApi.stopJob(id)
    const job = jobs.value.find((j) => j.id === id)
    if (job) job.status = 'completed'
    ElMessage.success('训练已结束，正在保存模型...')
  }

  async function fetchModels() {
    const res = await trainingApi.listModels()
    models.value = res.models
    return models.value
  }

  function connectWebSocket(jobId, onMessage) {
    if (wsConnections.value[jobId]) return

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/ws/training/${jobId}`
    const ws = new WebSocket(wsUrl)

    ws.onopen = () => {
      // Send ping every 25s
      const pingInterval = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send('ping')
      }, 25000)
      ws._pingInterval = pingInterval
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data !== 'pong') onMessage(data)
      } catch {}
    }

    ws.onclose = () => {
      if (ws._pingInterval) clearInterval(ws._pingInterval)
      delete wsConnections.value[jobId]
    }

    wsConnections.value[jobId] = ws
    return ws
  }

  function disconnectWebSocket(jobId) {
    const ws = wsConnections.value[jobId]
    if (ws) {
      ws.close()
      delete wsConnections.value[jobId]
    }
  }

  return {
    jobs,
    currentJob,
    models,
    loading,
    fetchJobs,
    createJob,
    fetchJob,
    cancelJob,
    stopJob,
    fetchModels,
    connectWebSocket,
    disconnectWebSocket,
  }
})
