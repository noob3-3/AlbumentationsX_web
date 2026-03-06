<template>
  <div>
    <div class="page-header">
      <h2>模型管理</h2>
      <p>管理已训练完成的 YOLO 模型</p>
    </div>

    <!-- Project Warning -->
    <el-alert
      v-if="!hasProject"
      type="warning"
      title="请先在页面顶部选择一个项目"
      description="选择项目后，将只显示该项目的模型"
      :closable="false"
      style="margin-bottom: 16px"
      show-icon
    />

    <el-card shadow="never">
      <template #header>
        <div style="display:flex;justify-content:space-between;align-items:center">
          <span>模型列表 ({{ models.length }})</span>
          <el-button size="small" :icon="Refresh" @click="loadModels">刷新</el-button>
        </div>
      </template>

      <el-empty v-if="!models.length" description="暂无训练完成的模型，请先完成训练任务" />

      <el-table v-else :data="models" stripe>
        <el-table-column prop="name" label="模型名称" min-width="160" />
        <el-table-column prop="model_type" label="类型" width="80" align="center">
          <template #default="{ row }">
            <el-tag size="small">{{ row.model_type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="类别" min-width="180">
          <template #default="{ row }">
            <el-tag
              v-for="cls in (row.classes || []).slice(0, 4)"
              :key="cls"
              size="small"
              style="margin: 2px"
            >{{ cls }}</el-tag>
            <span v-if="(row.classes || []).length > 4" style="color:#909399;font-size:12px">
              +{{ row.classes.length - 4 }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="mAP@0.5" width="100" align="center">
          <template #default="{ row }">
            <span v-if="row.map50 !== null" :class="mapColor(row.map50)">
              {{ (row.map50 * 100).toFixed(1) }}%
            </span>
            <span v-else style="color:#c0c4cc">-</span>
          </template>
        </el-table-column>
        <el-table-column label="mAP@0.5:0.95" width="120" align="center">
          <template #default="{ row }">
            <span v-if="row.map50_95 !== null">{{ (row.map50_95 * 100).toFixed(1) }}%</span>
            <span v-else style="color:#c0c4cc">-</span>
          </template>
        </el-table-column>
        <el-table-column label="文件大小" width="100" align="center">
          <template #default="{ row }">{{ formatSize(row.file_size) }}</template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="160">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-dropdown @command="(cmd) => handleDownload(cmd, row)" size="small">
              <el-button type="primary" size="small">
                下载 <el-icon class="el-icon--right"><arrow-down /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="weights">
                    <el-icon><Download /></el-icon>
                    仅权重文件 (best.pt)
                  </el-dropdown-item>
                  <el-dropdown-item command="package" divided>
                    <el-icon><FolderOpened /></el-icon>
                    完整包 (权重+标签+说明)
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { Refresh, Download, FolderOpened, ArrowDown } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { trainingApi } from '@/api'
import { useProjectStore } from '@/stores/project'
import { storeToRefs } from 'pinia'

const projectStore = useProjectStore()
const { hasProject, projectId } = storeToRefs(projectStore)

const models = ref([])

const formatDate = (d) => d ? new Date(d).toLocaleString('zh-CN', { hour12: false }) : '-'
const formatSize = (bytes) => {
  if (!bytes) return '-'
  if (bytes > 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${(bytes / 1024).toFixed(1)} KB`
}
const mapColor = (v) => v > 0.7 ? 'text-success' : v > 0.4 ? 'text-warning' : 'text-danger'

onMounted(loadModels)

watch(projectId, () => loadModels())

async function loadModels() {
  try {
    const params = {}
    if (projectId.value) {
      params.project_id = projectId.value
    }
    const res = await trainingApi.listModels(params)
    console.log('Models API response:', res)

    // Handle different response formats
    if (res.items && Array.isArray(res.items)) {
      models.value = res.items
    } else if (res.models && Array.isArray(res.models)) {
      models.value = res.models
    } else if (Array.isArray(res)) {
      models.value = res
    } else {
      console.error('Unexpected response format:', res)
      models.value = []
    }
  } catch (error) {
    console.error('Failed to load models:', error)
    ElMessage.error('加载模型列表失败: ' + (error.response?.data?.detail || error.message))
    models.value = []
  }
}

function handleDownload(command, model) {
  if (command === 'weights') {
    // 下载权重文件 (best.pt)
    ElMessage.info('正在下载模型权重文件 (best.pt)...')
    window.open(trainingApi.downloadModel(model.id), '_blank')
  } else if (command === 'package') {
    // 下载完整包 (权重 + 标签 + 说明)
    ElMessage.success('正在下载完整模型包 (包含权重、标签文件和使用说明)...')
    window.open(trainingApi.downloadModelPackage(model.id), '_blank')
  }
}
</script>

<style scoped>
.text-success { color: #67c23a; font-weight: 600; }
.text-warning { color: #e6a23c; font-weight: 600; }
.text-danger { color: #f56c6c; font-weight: 600; }
</style>
