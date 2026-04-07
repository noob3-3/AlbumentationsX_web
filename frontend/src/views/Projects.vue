<template>
  <div class="projects-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <span class="title">项目管理</span>
          <el-button type="primary" @click="openCreateDialog" :icon="Plus">
            新建项目
          </el-button>
        </div>
      </template>

      <!-- Search and filters -->
      <el-row :gutter="16" style="margin-bottom: 20px">
        <el-col :span="12">
          <el-input
            v-model="searchText"
            placeholder="搜索项目名称或描述"
            :prefix-icon="Search"
            clearable
            @input="onSearchInput"
          />
        </el-col>
        <el-col :span="12">
          <el-radio-group v-model="statusFilter" @change="onStatusFilterChange" class="status-filter-group">
            <el-radio-button label="all">全部</el-radio-button>
            <el-radio-button label="active">活跃</el-radio-button>
            <!-- 与后端 status=deleted 对应，界面统称「已归档」 -->
            <el-radio-button label="deleted">已归档</el-radio-button>
          </el-radio-group>
        </el-col>
      </el-row>

      <!-- Projects grid -->
      <div v-loading="loading" class="projects-grid">
        <div v-for="project in projects" :key="project.id" class="project-card">
          <el-card shadow="hover" :body-style="{ padding: '20px' }">
            <div class="project-header">
              <h3>{{ project.name }}</h3>
              <el-dropdown @command="handleCommand($event, project)">
                <el-icon class="more-icon"><MoreFilled /></el-icon>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="view">查看详情</el-dropdown-item>
                    <el-dropdown-item command="edit">编辑</el-dropdown-item>
                    <el-dropdown-item command="archive" v-if="project.status === 'active'">归档</el-dropdown-item>
                    <el-dropdown-item command="activate" v-if="isInactiveProject(project)">取消归档</el-dropdown-item>
                    <el-dropdown-item command="delete"
                                      v-if="project.status === 'active' || project.status === 'archived'" divided>
                      删除
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>

            <p class="project-desc">{{ project.description || '暂无描述' }}</p>

            <el-divider style="margin: 16px 0" />

            <el-row :gutter="16" class="project-stats">
              <el-col :span="12">
                <div class="stat-item">
                  <el-icon color="#409eff"><FolderOpened /></el-icon>
                  <span>{{ project.dataset_count }} 个数据集</span>
                </div>
              </el-col>
              <el-col :span="12">
                <div class="stat-item">
                  <el-icon color="#67c23a"><Box /></el-icon>
                  <span>{{ project.model_count }} 个模型</span>
                </div>
              </el-col>
            </el-row>

            <el-divider style="margin: 16px 0" />

            <div class="project-footer">
              <el-tag :type="projectStatusTagType(project.status)" size="small">
                {{ projectStatusLabel(project.status) }}
              </el-tag>
              <span class="project-date">{{ formatDate(project.created_at) }}</span>
            </div>

            <div class="project-actions">
              <el-button text @click="viewDatasets(project)">
                <el-icon><FolderOpened /></el-icon>
                数据集
              </el-button>
              <el-button text @click="viewModels(project)">
                <el-icon><Box /></el-icon>
                模型
              </el-button>
            </div>
          </el-card>
        </div>
      </div>

      <el-empty v-if="!loading && projects.length === 0" description="暂无项目，点击右上角创建新项目" />

      <!-- Pagination -->
      <el-pagination
        v-if="total > pageSize"
        v-model:current-page="currentPage"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[12, 24, 48]"
        layout="total, sizes, prev, pager, next"
        @current-change="loadProjects"
        @size-change="loadProjects"
        style="margin-top: 20px; justify-content: center"
      />
    </el-card>

    <!-- Create/Edit Project Dialog -->
    <el-dialog
      v-model="showCreateDialog"
      :title="editingProject ? '编辑项目' : '创建新项目'"
      width="600px"
      @close="resetForm"
    >
      <el-form :model="projectForm" :rules="formRules" ref="formRef" label-width="120px">
        <el-form-item label="项目名称" prop="name">
          <el-input v-model="projectForm.name" placeholder="请输入项目名称" />
        </el-form-item>
        <el-form-item label="项目描述" prop="description">
          <el-input
            v-model="projectForm.description"
            type="textarea"
            :rows="4"
            placeholder="请输入项目描述（可选）"
          />
        </el-form-item>

        <el-divider content-position="left">Webhook 配置</el-divider>

        <el-form-item label="启用 Webhook">
          <el-switch v-model="projectForm.webhook_enabled" />
          <span style="margin-left: 8px; color: #909399; font-size: 12px">
            任务状态变化时自动通知外部系统
          </span>
        </el-form-item>

        <template v-if="projectForm.webhook_enabled">
          <el-form-item label="Webhook URL" prop="webhook_url">
            <el-input
              v-model="projectForm.webhook_url"
              placeholder="https://your-domain.com/webhook"
            >
              <template #append>
                <el-button
                  :icon="Connection"
                  @click="testWebhookInDialog"
                  :loading="testingWebhook"
                  :disabled="!projectForm.webhook_url || !editingProject"
                >
                  测试
                </el-button>
              </template>
            </el-input>
            <div v-if="!editingProject" style="margin-top: 4px; color: #909399; font-size: 12px">
              保存项目后可测试 Webhook
            </div>
          </el-form-item>

          <el-form-item label="签名密钥" prop="webhook_secret">
            <el-input
              v-model="projectForm.webhook_secret"
              placeholder="用于验证请求来源（可选）"
              type="password"
              show-password
            />
          </el-form-item>

          <el-form-item label="订阅事件">
            <el-checkbox-group v-model="projectForm.webhook_events">
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
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="submitProject" :loading="submitting">
          {{ editingProject ? '保存' : '创建' }}
        </el-button>
      </template>
    </el-dialog>

    <!-- Project Details Dialog -->
    <el-dialog v-model="showDetailsDialog" title="项目详情" width="800px">
      <div v-if="selectedProject">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="项目名称">{{ selectedProject.name }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="projectStatusTagType(selectedProject.status)">
              {{ projectStatusLabel(selectedProject.status) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="数据集数量">{{ selectedProject.dataset_count }}</el-descriptions-item>
          <el-descriptions-item label="模型数量">{{ selectedProject.model_count }}</el-descriptions-item>
          <el-descriptions-item label="创建时间" :span="2">
            {{ formatDateTime(selectedProject.created_at) }}
          </el-descriptions-item>
          <el-descriptions-item label="更新时间" :span="2">
            {{ formatDateTime(selectedProject.updated_at) }}
          </el-descriptions-item>
          <el-descriptions-item label="项目描述" :span="2">
            {{ selectedProject.description || '暂无描述' }}
          </el-descriptions-item>
        </el-descriptions>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import {onMounted, ref} from 'vue'
import {ElMessage, ElMessageBox} from 'element-plus'
import {Box, Connection, FolderOpened, MoreFilled, Plus, Search} from '@element-plus/icons-vue'
import {useRouter} from 'vue-router'
import {useProjectStore} from '@/stores/project'
import {projectApi} from '@/api'

const router = useRouter()
const projectStore = useProjectStore()

const projects = ref([])
const loading = ref(false)
const searchText = ref('')
/** all=不传 status；勿用空字符串，易与 el-radio 的 value 解析不一致 */
const statusFilter = ref('all')
const currentPage = ref(1)
const pageSize = ref(12)
const total = ref(0)

const showCreateDialog = ref(false)
const showDetailsDialog = ref(false)
const editingProject = ref(null)
const selectedProject = ref(null)
const submitting = ref(false)
const testingWebhook = ref(false)
const formRef = ref(null)

const projectForm = ref({
  name: '',
  description: '',
  webhook_enabled: false,
  webhook_url: '',
  webhook_secret: '',
  webhook_events: [],
})

const formRules = {
  name: [
    { required: true, message: '请输入项目名称', trigger: 'blur' },
    { min: 1, max: 255, message: '长度在 1 到 255 个字符', trigger: 'blur' },
  ],
}

/** 后端 archived=归档；deleted=软删，标签统一用「归档」系文案，不用「删除」 */
function projectStatusLabel(status) {
  if (status === 'active') return '活跃'
  if (status === 'archived') return '已归档'
  if (status === 'deleted') return '归档'
  return status || '未知'
}

function projectStatusTagType(status) {
  if (status === 'active') return 'success'
  if (status === 'archived' || status === 'deleted') return 'info'
  return 'info'
}

function isInactiveProject(project) {
  return project.status === 'archived' || project.status === 'deleted'
}

onMounted(async () => {
  await loadProjects()
  await projectStore.syncHeaderProjects()
})

/** 切换状态筛选时回到第 1 页，并清空搜索（否则 search 与 status 叠加会经常筛出 0 条） */
function onStatusFilterChange() {
  currentPage.value = 1
  searchText.value = ''
  loadProjects()
}

function onSearchInput() {
  currentPage.value = 1
  loadProjects()
}

async function loadProjects() {
  loading.value = true
  try {
    const params = {
      page: currentPage.value,
      page_size: pageSize.value,
    }
    if (statusFilter.value !== 'all') {
      params.status = statusFilter.value
    }
    if (searchText.value) {
      params.search = searchText.value
    }

    const res = await projectApi.list(params)
    projects.value = res.items
    total.value = res.total
  } catch (error) {
    ElMessage.error('加载项目列表失败')
  } finally {
    loading.value = false
  }
}

function openCreateDialog() {
  editingProject.value = null
  resetForm()
  showCreateDialog.value = true
}

async function submitProject() {
  if (!formRef.value) return

  await formRef.value.validate(async (valid) => {
    if (!valid) return

    submitting.value = true
    try {
      if (editingProject.value) {
        await projectApi.update(editingProject.value.id, projectForm.value)
        ElMessage.success('项目已更新')
      } else {
        await projectApi.create(projectForm.value)
        ElMessage.success('项目已创建')
      }

      showCreateDialog.value = false
      await loadProjects()
      await projectStore.syncHeaderProjects()
    } catch (error) {
      ElMessage.error(error.response?.data?.detail || '操作失败')
    } finally {
      submitting.value = false
    }
  })
}

function handleCommand(command, project) {
  switch (command) {
    case 'view':
      selectedProject.value = project
      showDetailsDialog.value = true
      break
    case 'edit':
      editingProject.value = project
      projectForm.value = {
        name: project.name,
        description: project.description,
        webhook_enabled: project.webhook_enabled || false,
        webhook_url: project.webhook_url || '',
        webhook_secret: project.webhook_secret || '',
        webhook_events: project.webhook_events || [],
      }
      showCreateDialog.value = true
      break
    case 'archive':
      archiveProject(project)
      break
    case 'activate':
      activateProject(project)
      break
    case 'delete':
      deleteProject(project)
      break
  }
}

async function archiveProject(project) {
  try {
    await projectApi.update(project.id, {status: 'archived'})
    ElMessage.success('项目已归档')
    await loadProjects()
    await projectStore.syncHeaderProjects()
  } catch (error) {
    ElMessage.error('归档失败')
  }
}

async function activateProject(project) {
  try {
    await projectApi.update(project.id, {status: 'active'})
    ElMessage.success('已恢复为活跃项目')
    await loadProjects()
    await projectStore.fetchProjects()
    const p = projectStore.projects.find((x) => x.id === project.id)
    if (p) {
      projectStore.setCurrentProject(p)
    }
  } catch (error) {
    ElMessage.error('恢复失败')
  }
}

async function deleteProject(project) {
  try {
    await ElMessageBox.confirm('确定要删除该项目吗？此操作不可恢复。', '警告', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    })

    const wasCurrent = projectStore.currentProject?.id === project.id
    await projectApi.delete(project.id)
    ElMessage.success('项目已删除')
    await loadProjects()
    if (wasCurrent) {
      projectStore.clearCurrentProject()
    }
    await projectStore.fetchProjects()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

function viewDatasets(project) {
  router.push(`/datasets?project=${project.id}`)
}

function viewModels(project) {
  router.push(`/models?project=${project.id}`)
}

function formatDate(dateStr) {
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN')
}

function formatDateTime(dateStr) {
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN')
}

async function testWebhookInDialog() {
  if (!editingProject.value || !editingProject.value.id) {
    ElMessage.warning('请先保存项目后再测试 Webhook')
    return
  }

  testingWebhook.value = true
  try {
    await projectApi.testWebhook(editingProject.value.id)
    ElMessage.success('Webhook 测试成功！请检查您的接收端')
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || 'Webhook 测试失败')
  } finally {
    testingWebhook.value = false
  }
}

function resetForm() {
  projectForm.value = {
    name: '',
    description: '',
    webhook_enabled: false,
    webhook_url: '',
    webhook_secret: '',
    webhook_events: [],
  }
  editingProject.value = null
}
</script>

<style scoped>
.projects-page {
  padding: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.title {
  font-size: 18px;
  font-weight: 600;
}

.status-filter-group {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.projects-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 20px;
  min-height: 200px;
}

.project-card {
  transition: transform 0.2s;
}

.project-card:hover {
  transform: translateY(-2px);
}

.project-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
}

.project-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #303133;
  flex: 1;
}

.more-icon {
  font-size: 20px;
  cursor: pointer;
  color: #909399;
  transition: color 0.2s;
}

.more-icon:hover {
  color: #409eff;
}

.project-desc {
  margin: 0;
  font-size: 14px;
  color: #606266;
  line-height: 1.6;
  min-height: 44px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.project-stats {
  margin: 12px 0;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: #606266;
}

.project-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.project-date {
  font-size: 12px;
  color: #909399;
}
</style>

