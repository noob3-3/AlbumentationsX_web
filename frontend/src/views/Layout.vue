<template>
  <el-container style="height: 100vh">
    <!-- Sidebar -->
    <el-aside :width="collapsed ? '64px' : '220px'" class="sidebar">
      <div class="logo" :class="{ collapsed }">
        <svg v-if="collapsed" width="28" height="20" viewBox="0 0 42 20" xmlns="http://www.w3.org/2000/svg">
          <text x="0" y="16" font-family="Arial Black, Arial, sans-serif" font-weight="900" font-size="18" fill="#F5C542" letter-spacing="1">V</text>
        </svg>
        <svg v-else width="52" height="22" viewBox="0 0 52 22" xmlns="http://www.w3.org/2000/svg">
          <text x="0" y="18" font-family="Arial Black, Arial, sans-serif" font-weight="900" font-size="20" fill="#F5C542" letter-spacing="1">VST</text>
        </svg>
        <span v-if="!collapsed" class="logo-text">Platform</span>
      </div>

      <el-menu
        :default-active="currentRoute"
        :collapse="collapsed"
        background-color="#1e2130"
        text-color="#c0c4cc"
        active-text-color="#409eff"
        router
      >
        <el-menu-item
          v-for="item in menuItems"
          :key="item.path"
          :index="item.path"
        >
          <el-icon><component :is="item.icon" /></el-icon>
          <template #title>{{ item.title }}</template>
        </el-menu-item>
      </el-menu>

      <div class="collapse-btn" @click="collapsed = !collapsed">
        <el-icon><component :is="collapsed ? 'Expand' : 'Fold'" /></el-icon>
      </div>
    </el-aside>

    <!-- Main content -->
    <el-container>
      <el-header class="header">
        <div class="header-left">
          <span class="breadcrumb">{{ currentTitle }}</span>
        </div>
        <div class="header-center">
          <div class="project-selector">
            <span class="project-label">当前项目：</span>
            <el-select
              v-model="currentProjectId"
              placeholder="请选择项目"
              style="width: 240px"
              popper-class="layout-project-select-dropdown"
              @change="handleProjectChange"
              clearable
              filterable
            >
              <el-option
                v-for="project in projects"
                :key="project.id"
                :label="project.name"
                :value="project.id"
              >
                <div style="display: flex; justify-content: space-between; align-items: center">
                  <span>{{ project.name }}</span>
                  <el-tag size="small" type="info" style="margin-left: 8px">
                    {{ project.dataset_count || 0 }}数据集
                  </el-tag>
                </div>
              </el-option>
            </el-select>
          </div>
        </div>
        <div class="header-right">
          <el-tag type="success" size="small">v1.0.0</el-tag>
        </div>
      </el-header>

      <el-main class="main-content">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import {computed, onMounted, ref} from 'vue'
import {useRoute, useRouter} from 'vue-router'
import {useProjectStore} from '@/stores/project'
import {storeToRefs} from 'pinia'
import {ElMessage} from 'element-plus'

const route = useRoute()
const router = useRouter()
const collapsed = ref(false)

const projectStore = useProjectStore()
const { projects, currentProject } = storeToRefs(projectStore)

const currentProjectId = computed({
  get: () => currentProject.value?.id || null,
  set: (value) => {
    const project = projects.value.find(p => p.id === value)
    projectStore.setCurrentProject(project || null)
  }
})

onMounted(async () => {
  await projectStore.fetchProjects()
  // 如果没有选择项目，提示用户选择
  if (!currentProject.value && projects.value.length > 0) {
    ElMessage.info('请先选择一个项目')
  }
})

function handleProjectChange(projectId) {
  if (projectId) {
    const project = projects.value.find(p => p.id === projectId)
    if (project) {
      ElMessage.success(`已切换到项目：${project.name}`)
    }
  } else {
    ElMessage.info('已清除项目选择')
  }
}

const menuItems = [
  { path: '/dashboard', title: '概览', icon: 'Odometer' },
  { path: '/projects', title: '项目管理', icon: 'Management' },
  { path: '/collect', title: '数据采集', icon: 'Download' },
  { path: '/augmentation', title: '数据增强', icon: 'MagicStick' },
  { path: '/annotation', title: '数据标注', icon: 'EditPen' },
  { path: '/training', title: '模型训练', icon: 'Cpu' },
  { path: '/models', title: '模型管理', icon: 'Box' },
  { path: '/deployments', title: '模型部署', icon: 'Rocket' },
  { path: '/validation', title: '模型验证', icon: 'View' },
  { path: '/client-api', title: '客户端API', icon: 'Connection' },
]

const currentRoute = computed(() => '/' + route.path.split('/')[1])
const currentTitle = computed(
  () => menuItems.find((m) => m.path === currentRoute.value)?.title || '概览'
)
</script>

<style scoped>
.sidebar {
  background: #1e2130;
  transition: width 0.3s;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.logo {
  height: 60px;
  display: flex;
  align-items: center;
  padding: 0 20px;
  gap: 10px;
  border-bottom: 1px solid #2d3149;
  background: #161927;
  transition: padding 0.3s;
}

.logo.collapsed {
  padding: 0;
  justify-content: center;
}

.logo-text {
  color: #fff;
  font-size: 16px;
  font-weight: 700;
  white-space: nowrap;
}

.el-menu {
  border-right: none;
  flex: 1;
}

.el-menu-item.is-active {
  background-color: #1a3a5c !important;
  border-right: 3px solid #409eff;
}

.collapse-btn {
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: #909399;
  border-top: 1px solid #2d3149;
  transition: color 0.2s;
}
.collapse-btn:hover { color: #fff; }

.header {
  background: #fff;
  border-bottom: 1px solid #ebeef5;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  height: 60px;
}

.header-left {
  flex: 0 0 auto;
}

.header-center {
  flex: 1;
  display: flex;
  justify-content: center;
  align-items: center;
}

.header-right {
  flex: 0 0 auto;
}

.project-selector {
  display: flex;
  align-items: center;
  gap: 8px;
}

.project-label {
  font-size: 14px;
  color: #606266;
  font-weight: 500;
  white-space: nowrap;
}

.breadcrumb {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
}

.main-content {
  background: #f5f7fa;
  padding: 24px;
  overflow-y: auto;
}

.fade-enter-active, .fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from, .fade-leave-to {
  opacity: 0;
}
</style>

<!--
  下拉挂载到 body，需非 scoped。
  主题默认 .el-select-dropdown__wrap { max-height: 274px }，选项内自定义行（名称+标签）行高较大时约只能露出 6 条。
  需提高 max-height，并同时命中 .el-select-dropdown__wrap（与 .el-scrollbar__wrap 常为同一元素）。
-->
<style>
.layout-project-select-dropdown.el-select-dropdown > .el-scrollbar {
  height: auto !important;
  max-height: min(85vh, 720px) !important;
}

.layout-project-select-dropdown .el-select-dropdown__wrap,
.layout-project-select-dropdown .el-scrollbar__wrap {
  max-height: min(85vh, 720px) !important;
}
</style>
