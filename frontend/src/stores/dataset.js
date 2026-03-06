import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { datasetApi } from '@/api'
import { ElMessage } from 'element-plus'
import { useProjectStore } from './project'

export const useDatasetStore = defineStore('dataset', () => {
  const datasets = ref([])
  const currentDataset = ref(null)
  const total = ref(0)
  const loading = ref(false)
  const images = ref([])
  const imageTotal = ref(0)

  async function fetchDatasets(params = {}) {
    loading.value = true
    try {
      const projectStore = useProjectStore()
      // 如果有当前项目，自动过滤
      const projectId = projectStore.projectId
      if (projectId && !params.project_id) {
        params.project_id = projectId
      }
      const res = await datasetApi.list({ page: 1, page_size: 50, ...params })
      datasets.value = res.items
      total.value = res.total
    } finally {
      loading.value = false
    }
  }

  async function createDataset(data) {
    const dataset = await datasetApi.create(data)
    datasets.value.unshift(dataset)
    total.value++
    ElMessage.success('数据集创建成功')
    return dataset
  }

  async function fetchDataset(id) {
    loading.value = true
    try {
      currentDataset.value = await datasetApi.get(id)
    } finally {
      loading.value = false
    }
  }

  async function deleteDataset(id) {
    await datasetApi.delete(id)
    datasets.value = datasets.value.filter((d) => d.id !== id)
    total.value--
    ElMessage.success('数据集已删除')
  }

  async function fetchImages(datasetId, params = {}) {
    loading.value = true
    try {
      const res = await datasetApi.listImages(datasetId, { page: 1, page_size: 50, ...params })
      images.value = res.items
      imageTotal.value = res.total
    } finally {
      loading.value = false
    }
  }

  return {
    datasets,
    currentDataset,
    total,
    loading,
    images,
    imageTotal,
    fetchDatasets,
    createDataset,
    fetchDataset,
    deleteDataset,
    fetchImages,
  }
})
