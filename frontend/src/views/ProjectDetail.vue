<template>
  <div class="project-detail-page">
    <!-- Breadcrumb -->
    <el-breadcrumb separator="/" style="margin-bottom: 20px">
      <el-breadcrumb-item :to="{ path: '/projects' }">项目管理</el-breadcrumb-item>
      <el-breadcrumb-item>{{ project?.name || '加载中...' }}</el-breadcrumb-item>
    </el-breadcrumb>

    <div v-loading="loading">
      <!-- Project Info Card -->
      <el-card v-if="project" class="project-info-card">
        <template #header>
          <div class="card-header">
            <div>
              <h2 style="margin: 0">{{ project.name }}</h2>
              <p style="margin: 8px 0 0 0; color: #909399">{{ project.description || '暂无描述' }}</p>
            </div>
            <div style="display: flex; gap: 8px">
              <el-button @click="showEditDialog = true" :icon="Edit">编辑</el-button>
              <el-dropdown @command="handleProjectCommand">
                <el-button :icon="MoreFilled">更多</el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="archive" v-if="project.status === 'active'">
                      <el-icon><FolderDelete /></el-icon>归档项目
                    </el-dropdown-item>
                    <el-dropdown-item command="activate" v-if="project.status === 'archived'">
                      <el-icon><FolderOpened /></el-icon>激活项目
                    </el-dropdown-item>
                    <el-dropdown-item command="delete" divided>
                      <el-icon><Delete /></el-icon>删除项目
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </div>
        </template>

        <!-- Statistics -->
        <el-row :gutter="20">
          <el-col :span="6">
            <el-statistic title="数据集" :value="project.dataset_count">
              <template #prefix>
                <el-icon color="#409eff"><FolderOpened /></el-icon>
              </template>
            </el-statistic>
          </el-col>
          <el-col :span="6">
            <el-statistic title="模型" :value="project.model_count">
              <template #prefix>
                <el-icon color="#67c23a"><Box /></el-icon>
              </template>
            </el-statistic>
          </el-col>
          <el-col :span="6">
            <el-statistic title="总图片" :value="totalImages">
              <template #prefix>
                <el-icon color="#e6a23c"><Picture /></el-icon>
              </template>
            </el-statistic>
          </el-col>
          <el-col :span="6">
            <el-statistic title="总标注" :value="totalAnnotations">
              <template #prefix>
                <el-icon color="#f56c6c"><EditPen /></el-icon>
              </template>
            </el-statistic>
          </el-col>
        </el-row>
      </el-card>

      <!-- Tabs for Datasets and Models -->
      <el-card style="margin-top: 20px">
        <el-tabs v-model="activeTab">
          <!-- Datasets Tab -->
          <el-tab-pane label="数据集" name="datasets">
            <template #label>
              <span><el-icon><FolderOpened /></el-icon> 数据集 ({{ datasets.length }})</span>
            </template>

            <div style="margin-bottom: 16px">
              <el-button type="primary" @click="showCreateDatasetDialog = true" :icon="Plus">
                新建数据集
              </el-button>
            </div>

            <el-table :data="datasets" v-loading="datasetsLoading" stripe>
              <el-table-column prop="name" label="名称" min-width="160">
                <template #default="{ row }">
                  <el-link type="primary" @click="$router.push(`/datasets/${row.id}`)">
                    {{ row.name }}
                  </el-link>
                </template>
              </el-table-column>
              <el-table-column prop="description" label="描述" min-width="200" show-overflow-tooltip />
              <el-table-column label="图片" width="120" align="center">
                <template #default="{ row }">
                  <el-tag size="small">原始: {{ row.image_count - row.augmented_count }}</el-tag>
                  <el-tag size="small" type="warning" v-if="row.augmented_count > 0">
                    增强: {{ row.augmented_count }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="annotation_count" label="标注数" width="100" align="center" />
              <el-table-column label="类别" min-width="160">
                <template #default="{ row }">
                  <el-tag
                    v-for="cls in (row.classes || []).slice(0, 3)"
                    :key="cls"
                    size="small"
                    style="margin: 2px"
                  >{{ cls }}</el-tag>
                  <span v-if="(row.classes || []).length > 3" style="color: #909399; font-size: 12px">
                    +{{ row.classes.length - 3 }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column label="状态" width="100" align="center">
                <template #default="{ row }">
                  <el-tag :type="getStatusType(row.status)" size="small">{{ row.status }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="240" fixed="right">
                <template #default="{ row }">
                  <el-button link type="primary" size="small" @click="$router.push(`/datasets/${row.id}`)">
                    查看
                  </el-button>
                  <el-button link type="primary" size="small" @click="$router.push(`/collect?dataset=${row.id}`)">
                    采集
                  </el-button>
                  <el-button link type="primary" size="small" @click="$router.push(`/annotation?dataset=${row.id}`)">
                    标注
                  </el-button>
                  <el-popconfirm title="确认删除?" @confirm="deleteDataset(row.id)">
                    <template #reference>
                      <el-button link type="danger" size="small">删除</el-button>
                    </template>
                  </el-popconfirm>
                </template>
              </el-table-column>
            </el-table>

            <el-empty v-if="!datasetsLoading && datasets.length === 0" description="暂无数据集" />
          </el-tab-pane>

          <!-- Models Tab -->
          <el-tab-pane label="模型" name="models">
            <template #label>
              <span><el-icon><Box /></el-icon> 模型 ({{ models.length }})</span>
            </template>

            <el-table :data="models" v-loading="modelsLoading" stripe>
              <el-table-column prop="name" label="模型名称" min-width="180">
                <template #default="{ row }">
                  <div style="display: flex; align-items: center; gap: 8px">
                    <span>{{ row.name }}</span>
                    <el-tag v-if="row.is_deployed" type="success" size="small">已部署</el-tag>
                  </div>
                </template>
              </el-table-column>
              <el-table-column prop="model_type" label="类型" width="100" align="center">
                <template #default="{ row }">
                  <el-tag size="small">{{ row.model_type }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="mAP" width="180" align="center">
                <template #default="{ row }">
                  <div v-if="row.map50">
                    <el-tag size="small" type="success">
                      mAP50: {{ (row.map50 * 100).toFixed(1) }}%
                    </el-tag>
                    <el-tag size="small" type="info" v-if="row.map50_95" style="margin-left: 4px">
                      mAP50-95: {{ (row.map50_95 * 100).toFixed(1) }}%
                    </el-tag>
                  </div>
                  <span v-else style="color: #909399">-</span>
                </template>
              </el-table-column>
              <el-table-column label="文件大小" width="120" align="center">
                <template #default="{ row }">
                  {{ formatFileSize(row.file_size) }}
                </template>
              </el-table-column>
              <el-table-column prop="created_at" label="创建时间" width="160">
                <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
              </el-table-column>
              <el-table-column label="操作" width="200" fixed="right">
                <template #default="{ row }">
                  <el-button link type="primary" size="small" @click="validateModel(row)">
                    验证
                  </el-button>
                  <el-button link type="primary" size="small" @click="deployModel(row)">
                    部署
                  </el-button>
                  <el-button link type="primary" size="small" @click="downloadModel(row)">
                    下载
                  </el-button>
                </template>
              </el-table-column>
            </el-table>

            <el-empty v-if="!modelsLoading && models.length === 0" description="暂无模型" />
          </el-tab-pane>
        </el-tabs>
      </el-card>
    </div>

    <!-- Edit Project Dialog -->
    <el-dialog v-model="showEditDialog" title="编辑项目" width="600px">
      <el-form :model="editForm" label-width="120px" ref="editFormRef">
        <el-form-item label="项目名称" prop="name">
          <el-input v-model="editForm.name" />
        </el-form-item>
        <el-form-item label="项目描述">
          <el-input v-model="editForm.description" type="textarea" :rows="4" />
        </el-form-item>

        <el-divider content-position="left">Webhook 配置</el-divider>

        <el-form-item label="启用 Webhook">
          <el-switch v-model="editForm.webhook_enabled" />
          <span style="margin-left: 8px; color: #909399; font-size: 12px">
            任务状态变化时自动通知外部系统
          </span>
        </el-form-item>

        <template v-if="editForm.webhook_enabled">
          <el-form-item label="Webhook URL" prop="webhook_url">
            <el-input
              v-model="editForm.webhook_url"
              placeholder="https://your-domain.com/webhook"
            >
              <template #append>
                <el-button
                  :icon="Connection"
                  @click="testWebhook"
                  :loading="testingWebhook"
                  :disabled="!editForm.webhook_url"
                >
                  测试
                </el-button>
              </template>
            </el-input>
          </el-form-item>

          <el-form-item label="签名密钥" prop="webhook_secret">
            <el-input
              v-model="editForm.webhook_secret"
              placeholder="用于验证请求来源（可选）"
              type="password"
              show-password
            />
          </el-form-item>

          <el-form-item label="订阅事件">
            <el-checkbox-group v-model="editForm.webhook_events">
              <el-checkbox label="training">训练任务</el-checkbox>
              <el-checkbox label="augmentation">数据增强</el-checkbox>
              <el-checkbox label="annotation">自动标注</el-checkbox>
            </el-checkbox-group>
            <div style="margin-top: 4px; color: #909399; font-size: 12px">
              选择需要接收通知的事件类型
            </div>
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" @click="updateProject" :loading="updating">保存</el-button>
      </template>
    </el-dialog>

    <!-- Create Dataset Dialog -->
    <el-dialog v-model="showCreateDatasetDialog" title="新建数据集" width="500px">
      <el-form :model="datasetForm" label-width="100px" ref="datasetFormRef">
        <el-form-item label="数据集名称" prop="name" required>
          <el-input v-model="datasetForm.name" placeholder="输入数据集名称" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="datasetForm.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="类别">
          <el-select
            v-model="datasetForm.classes"
            multiple
            filterable
            allow-create
            placeholder="输入类别名称后回车添加"
            style="width: 100%"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDatasetDialog = false">取消</el-button>
        <el-button type="primary" @click="createDataset" :loading="creatingDataset">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Edit, MoreFilled, Plus, FolderOpened, FolderDelete, Delete, Box, Picture, EditPen, Connection
} from '@element-plus/icons-vue'
import { projectApi, datasetApi } from '@/api'

const route = useRoute()
const router = useRouter()

const projectId = computed(() => route.params.id)
const loading = ref(false)
const datasetsLoading = ref(false)
const modelsLoading = ref(false)
const updating = ref(false)
const creatingDataset = ref(false)
const testingWebhook = ref(false)

const project = ref(null)
const datasets = ref([])
const models = ref([])
const activeTab = ref('datasets')

const showEditDialog = ref(false)
const showCreateDatasetDialog = ref(false)
const editFormRef = ref(null)
const datasetFormRef = ref(null)

const editForm = ref({
  name: '',
  description: '',
  webhook_enabled: false,
  webhook_url: '',
  webhook_secret: '',
  webhook_events: [],
})

const datasetForm = ref({
  name: '',
  description: '',
  classes: [],
})

const totalImages = computed(() => {
  return datasets.value.reduce((sum, ds) => sum + (ds.image_count || 0), 0)
})

const totalAnnotations = computed(() => {
  return datasets.value.reduce((sum, ds) => sum + (ds.annotation_count || 0), 0)
})

onMounted(() => {
  loadProject()
  loadDatasets()
  loadModels()
})

watch(() => route.params.id, () => {
  if (route.params.id) {
    loadProject()
    loadDatasets()
    loadModels()
  }
})

async function loadProject() {
  if (!projectId.value) return

  loading.value = true
  try {
    project.value = await projectApi.get(projectId.value)
    editForm.value = {
      name: project.value.name,
      description: project.value.description,
      webhook_enabled: project.value.webhook_enabled || false,
      webhook_url: project.value.webhook_url || '',
      webhook_secret: project.value.webhook_secret || '',
      webhook_events: project.value.webhook_events || [],
    }
  } catch (error) {
    ElMessage.error('加载项目失败')
    router.push('/projects')
  } finally {
    loading.value = false
  }
}

async function loadDatasets() {
  if (!projectId.value) return

  datasetsLoading.value = true
  try {
    const res = await projectApi.getDatasets(projectId.value, { page: 1, page_size: 100 })
    datasets.value = res.items
  } catch (error) {
    ElMessage.error('加载数据集失败')
  } finally {
    datasetsLoading.value = false
  }
}

async function loadModels() {
  if (!projectId.value) return

  modelsLoading.value = true
  try {
    const res = await projectApi.getModels(projectId.value, { page: 1, page_size: 100 })
    models.value = res.items
  } catch (error) {
    ElMessage.error('加载模型失败')
  } finally {
    modelsLoading.value = false
  }
}

async function updateProject() {
  updating.value = true
  try {
    await projectApi.update(projectId.value, editForm.value)
    ElMessage.success('项目已更新')
    showEditDialog.value = false
    loadProject()
  } catch (error) {
    ElMessage.error('更新失败')
  } finally {
    updating.value = false
  }
}

async function createDataset() {
  if (!datasetFormRef.value) return

  creatingDataset.value = true
  try {
    const data = {
      ...datasetForm.value,
      project_id: projectId.value,
    }
    await datasetApi.create(data)
    ElMessage.success('数据集已创建')
    showCreateDatasetDialog.value = false
    datasetForm.value = { name: '', description: '', classes: [] }
    loadDatasets()
    await projectApi.updateCounts(projectId.value)
    loadProject()
  } catch (error) {
    ElMessage.error('创建失败')
  } finally {
    creatingDataset.value = false
  }
}

async function deleteDataset(datasetId) {
  try {
    await datasetApi.delete(datasetId)
    ElMessage.success('数据集已删除')
    loadDatasets()
    await projectApi.updateCounts(projectId.value)
    loadProject()
  } catch (error) {
    ElMessage.error('删除失败')
  }
}

async function testWebhook() {
  if (!projectId.value) return

  testingWebhook.value = true
  try {
    await projectApi.testWebhook(projectId.value)
    ElMessage.success('Webhook 测试成功！请检查您的接收端')
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || 'Webhook 测试失败')
  } finally {
    testingWebhook.value = false
  }
}

async function handleProjectCommand(command) {
  switch (command) {
    case 'archive':
      await projectApi.update(projectId.value, { status: 'archived' })
      ElMessage.success('项目已归档')
      loadProject()
      break
    case 'activate':
      await projectApi.update(projectId.value, { status: 'active' })
      ElMessage.success('项目已激活')
      loadProject()
      break
    case 'delete':
      try {
        await ElMessageBox.confirm('确定要删除该项目吗？', '警告', {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          type: 'warning',
        })
        await projectApi.delete(projectId.value)
        ElMessage.success('项目已删除')
        router.push('/projects')
      } catch (error) {
        if (error !== 'cancel') {
          ElMessage.error('删除失败')
        }
      }
      break
  }
}

function validateModel(model) {
  router.push({ path: '/validation', query: { model_id: model.id } })
}

function deployModel(model) {
  router.push({ path: '/deployments', query: { model_id: model.id } })
}

function downloadModel(model) {
  window.open(`/api/v1/models/${model.id}/download`, '_blank')
}

function getStatusType(status) {
  const types = {
    active: 'success',
    ready: 'success',
    pending: 'info',
    augmenting: 'warning',
    error: 'danger',
  }
  return types[status] || 'info'
}

function formatDate(dateStr) {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN')
}

function formatFileSize(bytes) {
  if (!bytes) return '-'
  const mb = bytes / 1024 / 1024
  if (mb > 1024) {
    return (mb / 1024).toFixed(2) + ' GB'
  }
  return mb.toFixed(2) + ' MB'
}
</script>

<style scoped>
.project-detail-page {
  padding: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.project-info-card {
  border-top: 4px solid #409eff;
}
</style>

