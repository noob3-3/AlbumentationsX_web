import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { projectApi } from '@/api'

export const useProjectStore = defineStore('project', () => {
  const currentProject = ref(null)
  const projects = ref([])
  const loading = ref(false)

  // 从 localStorage 恢复当前项目
  const savedProjectId = localStorage.getItem('currentProjectId')
  if (savedProjectId) {
    // 异步加载项目信息
    projectApi.get(savedProjectId).then((project) => {
      currentProject.value = project
    }).catch(() => {
      localStorage.removeItem('currentProjectId')
    })
  }

  async function fetchProjects() {
    loading.value = true
    try {
      const res = await projectApi.list({ page: 1, page_size: 100, status: 'active' })
      projects.value = res.items
      return res.items
    } finally {
      loading.value = false
    }
  }

  function setCurrentProject(project) {
    currentProject.value = project
    if (project) {
      localStorage.setItem('currentProjectId', project.id)
    } else {
      localStorage.removeItem('currentProjectId')
    }
  }

  function clearCurrentProject() {
    currentProject.value = null
    localStorage.removeItem('currentProjectId')
  }

  const hasProject = computed(() => !!currentProject.value)
  const projectId = computed(() => currentProject.value?.id || null)
  const projectName = computed(() => currentProject.value?.name || '未选择项目')

  return {
    currentProject,
    projects,
    loading,
    hasProject,
    projectId,
    projectName,
    fetchProjects,
    setCurrentProject,
    clearCurrentProject,
  }
})

