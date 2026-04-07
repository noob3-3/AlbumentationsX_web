import {defineStore} from 'pinia'
import {computed, ref} from 'vue'
import {projectApi} from '@/api'

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
        const pageSize = 100
        let page = 1
        const all = []
        let total = Infinity
        while (all.length < total) {
            const res = await projectApi.list({page, page_size: pageSize, status: 'active'})
            total = res.total ?? res.items?.length ?? 0
            all.push(...(res.items || []))
            if (!res.items?.length || res.items.length < pageSize) break
            page += 1
        }
        projects.value = all
        return all
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

    /** 顶部下拉与活跃项目列表同步；若当前选中已不在活跃列表中则清空 */
    async function syncHeaderProjects() {
        const prevId = currentProject.value?.id
        await fetchProjects()
        if (!prevId) return
        const fresh = projects.value.find((p) => p.id === prevId)
        if (fresh) {
            setCurrentProject(fresh)
        } else {
            clearCurrentProject()
        }
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
      syncHeaderProjects,
    setCurrentProject,
    clearCurrentProject,
  }
})

