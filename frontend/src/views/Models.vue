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
          <div style="display:flex;gap:8px">
            <el-button type="primary" size="small" :icon="Upload" @click="showImportDialog">导入模型</el-button>
            <el-button size="small" :icon="Refresh" @click="loadModels">刷新</el-button>
          </div>
        </div>
      </template>

      <el-empty v-if="!models.length" description="暂无模型，可训练或导入模型" />

      <!-- 导入模型对话框 -->
      <el-dialog
        v-model="importDialogVisible"
        title="导入模型"
        width="520px"
        :close-on-click-modal="false"
        @closed="resetImportForm"
      >
        <el-form ref="importFormRef" :model="importForm" :rules="importRules" label-width="100px">
          <el-form-item label="模型名称" prop="name">
            <el-input v-model="importForm.name" placeholder="请输入模型名称" maxlength="255" show-word-limit />
          </el-form-item>
          <el-form-item label="权重文件" prop="file" required>
            <el-upload
              ref="uploadRef"
              :auto-upload="false"
              :limit="1"
              accept=".pt"
              :on-change="onImportFileChange"
              :on-remove="() => importForm.file = null"
              :on-exceed="() => ElMessage.warning('仅支持上传一个 .pt 文件')"
            >
              <template #trigger>
                <el-button type="primary" plain>选择 .pt 文件</el-button>
              </template>
              <template #tip>
                <div class="el-upload__tip">支持 YOLO 格式权重文件，最大 500MB</div>
              </template>
            </el-upload>
          </el-form-item>
          <el-form-item label="类别（可选）">
            <el-input
              v-model="importForm.classes"
              type="textarea"
              :rows="3"
              placeholder="逗号分隔，如：人,车,狗。不填则尝试从模型中自动提取"
            />
          </el-form-item>
          <el-form-item label="或上传类别文件">
            <el-upload
              :auto-upload="false"
              :limit="1"
              accept=".txt"
              :on-change="onClassesFileChange"
              :on-remove="() => importForm.classesFile = null"
            >
              <template #trigger>
                <el-button size="small" plain>选择 classes.txt</el-button>
              </template>
            </el-upload>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="importDialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="importing" @click="submitImport">
            导入
          </el-button>
        </template>
      </el-dialog>

      <el-table v-if="models.length" :data="models" stripe>
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
        <el-table-column label="操作" width="200" fixed="right">
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
            <el-popconfirm
              v-if="!row.is_deployed"
              title="确认删除此模型？"
              @confirm="deleteModel(row)"
            >
              <template #reference>
                <el-button type="danger" size="small" :icon="Delete" plain style="margin-left: 8px">
                  删除
                </el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { Refresh, Download, FolderOpened, ArrowDown, Delete, Upload } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { trainingApi } from '@/api'
import { useProjectStore } from '@/stores/project'
import { storeToRefs } from 'pinia'

const projectStore = useProjectStore()
const { hasProject, projectId } = storeToRefs(projectStore)

const models = ref([])
const importDialogVisible = ref(false)
const importing = ref(false)
const importFormRef = ref(null)
const uploadRef = ref(null)
const importForm = ref({
  name: '',
  file: null,
  classes: '',
  classesFile: null,
})
const importRules = {
  name: [{ required: true, message: '请输入模型名称', trigger: 'blur' }],
}

function showImportDialog() {
  importDialogVisible.value = true
}

function onImportFileChange(file) {
  importForm.value.file = file.raw || file
}

function onClassesFileChange(file) {
  importForm.value.classesFile = file.raw || file
}

function resetImportForm() {
  importForm.value = { name: '', file: null, classes: '', classesFile: null }
  uploadRef.value?.clearFiles?.()
  importFormRef.value?.resetFields?.()
}

async function submitImport() {
  if (!importForm.value.file) {
    ElMessage.warning('请选择要导入的 .pt 文件')
    return
  }
  if (!importForm.value.name?.trim()) {
    ElMessage.warning('请输入模型名称')
    return
  }
  importing.value = true
  try {
    const formData = new FormData()
    formData.append('file', importForm.value.file)
    formData.append('name', importForm.value.name.trim())
    if (projectId.value) {
      formData.append('project_id', projectId.value)
    }
    if (importForm.value.classes?.trim()) {
      formData.append('classes_str', importForm.value.classes.trim())
    }
    if (importForm.value.classesFile) {
      formData.append('classes_file', importForm.value.classesFile)
    }
    await trainingApi.importModel(formData)
    ElMessage.success('模型导入成功')
    importDialogVisible.value = false
    loadModels()
  } catch (error) {
    ElMessage.error('导入失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    importing.value = false
  }
}

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

async function deleteModel(model) {
  try {
    await trainingApi.deleteModel(model.id)
    ElMessage.success('模型已删除')
    loadModels()
  } catch (error) {
    ElMessage.error('删除失败: ' + (error.response?.data?.detail || error.message))
  }
}
</script>

<style scoped>
.text-success { color: #67c23a; font-weight: 600; }
.text-warning { color: #e6a23c; font-weight: 600; }
.text-danger { color: #f56c6c; font-weight: 600; }
</style>
