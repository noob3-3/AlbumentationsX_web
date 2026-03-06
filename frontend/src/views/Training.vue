<template>
  <div>
    <div class="page-header">
      <h2>模型训练</h2>
      <p>使用 Ultralytics YOLO 训练目标检测模型</p>
    </div>

    <!-- Project Warning -->
    <el-alert
      v-if="!hasProject"
      type="warning"
      title="请先在页面顶部选择一个项目"
      description="选择项目后，下方数据集和模型列表将只显示该项目的数据"
      :closable="false"
      style="margin-bottom: 16px"
      show-icon
    />

    <el-row :gutter="16">
      <!-- Create Training Job -->
      <el-col :span="10">
        <el-card shadow="never">
          <template #header><span>创建训练任务</span></template>
          <el-form :model="form" :rules="rules" ref="formRef" label-width="100px">
            <el-form-item label="任务名称" prop="name">
              <el-input
                v-model="form.name"
                :disabled="!hasProject"
                placeholder="选择数据集和模型后自动生成（可手动修改）"
              />
            </el-form-item>
            <el-form-item label="数据集" prop="dataset_id">
              <el-select
                v-model="form.dataset_id"
                placeholder="选择数据集"
                style="width:100%"
                :disabled="!hasProject"
              >
                <el-option
                  v-for="d in datasets"
                  :key="d.id"
                  :label="`${d.name} (${d.image_count}张)`"
                  :value="d.id"
                />
              </el-select>
              <span v-if="!hasProject" class="hint">请先选择项目</span>
              <span v-else-if="datasets.length === 0" class="hint">当前项目暂无数据集</span>

              <!-- 数据集信息提示 -->
              <div v-if="selectedDatasetInfo" style="margin-top: 8px">
                <el-alert
                  v-if="selectedDatasetInfo.augmented_count > 0 && selectedDatasetInfo.unlabeled_augmented_count > 0"
                  type="warning"
                  :closable="false"
                  show-icon
                >
                  <template #title>
                    <div style="font-size: 12px">
                      数据集包含 {{ selectedDatasetInfo.augmented_count }} 张增强数据
                      （已标注 {{ selectedDatasetInfo.augmented_annotated_count }} 张，
                      未标注 {{ selectedDatasetInfo.unlabeled_augmented_count }} 张）。
                      训练时仅使用已标注的图片。
                      <el-link type="primary" :underline="false" @click="goToAnnotation" style="margin-left: 8px">
                        去标注 →
                      </el-link>
                    </div>
                  </template>
                </el-alert>
                <el-alert
                  v-else-if="selectedDatasetInfo.augmented_count > 0"
                  type="success"
                  :closable="false"
                  show-icon
                >
                  <template #title>
                    <div style="font-size: 12px">
                      数据集包含 {{ selectedDatasetInfo.original_count }} 张原始图片 +
                      {{ selectedDatasetInfo.augmented_count }} 张增强图片，共 {{ selectedDatasetInfo.image_count }} 张
                      （已标注 {{ selectedDatasetInfo.annotated_image_count }} 张）
                    </div>
                  </template>
                </el-alert>
                <el-alert
                  v-else
                  type="info"
                  :closable="false"
                  show-icon
                >
                  <template #title>
                    <div style="font-size: 12px">
                      数据集包含 {{ selectedDatasetInfo.original_count }} 张原始图片
                      （已标注 {{ selectedDatasetInfo.original_annotated_count }} 张），未使用数据增强
                    </div>
                  </template>
                </el-alert>
              </div>
            </el-form-item>

            <!-- 使用增强数据选项 -->
            <el-form-item v-if="selectedDatasetInfo && selectedDatasetInfo.augmented_count > 0">
              <el-checkbox v-model="form.use_augmented_data">
                <span style="font-weight: 500">使用增强数据进行训练</span>
              </el-checkbox>
              <div style="margin-top: 4px; color: #909399; font-size: 12px; margin-left: 24px">
                取消勾选则仅使用 {{ selectedDatasetInfo.original_count }} 张原始图片训练
              </div>
            </el-form-item>

            <el-form-item label="基础模型">
              <el-select v-model="form.model_name" style="width:100%">
                <el-option-group label="YOLO11">
                  <el-option v-for="m in yolo11Models" :key="m" :label="m" :value="m" />
                </el-option-group>
                <el-option-group label="YOLOv8">
                  <el-option v-for="m in yolov8Models" :key="m" :label="m" :value="m" />
                </el-option-group>
              </el-select>
            </el-form-item>

            <el-divider />

            <!-- 继续训练选项 -->
            <el-form-item>
              <el-checkbox v-model="form.resume_training" @change="onResumeTrainingChange">
                <span style="font-weight: 500">继续训练（从已有模型继续）</span>
              </el-checkbox>
            </el-form-item>

            <el-form-item
              v-if="form.resume_training"
              label="选择模型"
              prop="base_model_id"
            >
              <el-select
                v-model="form.base_model_id"
                placeholder="选择要继续训练的模型"
                style="width:100%"
              >
                <el-option
                  v-for="m in availableModels"
                  :key="m.id"
                  :label="`${m.name} (mAP50: ${(m.map50 * 100).toFixed(1)}%)`"
                  :value="m.id"
                />
              </el-select>
              <el-alert
                style="margin-top: 8px"
                type="info"
                :closable="false"
              >
                <template #title>
                  <span style="font-size: 12px">
                    继续训练可以在已有模型基础上微调，提升特定场景的精度
                  </span>
                </template>
              </el-alert>
            </el-form-item>

            <el-divider />

            <!-- 类别增强训练 -->
            <el-form-item>
              <el-checkbox v-model="form.use_class_enhancement">
                <span style="font-weight: 500">类别增强（对特定类别加强训练）</span>
              </el-checkbox>
            </el-form-item>

            <el-form-item
              v-if="form.use_class_enhancement"
              label="重点类别"
            >
              <el-select
                v-model="form.focus_classes"
                multiple
                placeholder="选择要加强训练的类别"
                style="width:100%"
              >
                <el-option
                  v-for="cls in datasetClasses"
                  :key="cls"
                  :label="cls"
                  :value="cls"
                />
              </el-select>
              <el-alert
                style="margin-top: 8px"
                type="warning"
                :closable="false"
              >
                <template #title>
                  <span style="font-size: 12px">
                    对选中的类别使用更强的数据增强（Mosaic、Copy-Paste），提升识别能力
                  </span>
                </template>
              </el-alert>
            </el-form-item>

            <el-divider>训练参数</el-divider>

            <el-form-item label="训练轮数">
              <el-input-number v-model="form.epochs" :min="1" :max="1000" />
            </el-form-item>
            <el-form-item label="批大小">
              <el-input-number v-model="form.batch_size" :min="1" :max="512" />
            </el-form-item>
            <el-form-item label="图片尺寸">
              <el-select v-model="form.img_size" style="width:200px">
                <el-option :value="320" label="320" />
                <el-option :value="416" label="416" />
                <el-option :value="640" label="640 (推荐)" />
                <el-option :value="1280" label="1280" />
              </el-select>
            </el-form-item>
            <el-form-item label="学习率">
              <el-input-number v-model="form.learning_rate" :min="0.0001" :max="0.1" :step="0.001" :precision="4" />
            </el-form-item>
            <el-form-item label="验证集比例">
              <el-slider v-model="form.val_split" :min="0.1" :max="0.4" :step="0.05" :format-tooltip="(v) => `${(v*100).toFixed(0)}%`" style="width:200px" />
              <span style="margin-left:12px">{{ (form.val_split * 100).toFixed(0) }}%</span>
            </el-form-item>
            <el-form-item label="设备">
              <el-radio-group v-model="form.device">
                <el-radio value="auto">自动</el-radio>
                <el-radio value="cpu">CPU</el-radio>
                <el-radio value="0">GPU 0</el-radio>
              </el-radio-group>
            </el-form-item>

            <el-divider />

            <!-- 早停和保存策略 -->
            <el-form-item label="早停耐心值">
              <el-input-number
                v-model="form.patience"
                :min="0"
                :max="200"
                style="width: 150px"
              />
              <el-text size="small" type="info" style="margin-left: 12px">
                连续N轮验证指标不改善则停止，0表示不启用
              </el-text>
            </el-form-item>

            <el-form-item label="保存策略">
              <el-input-number
                v-model="form.save_period"
                :min="-1"
                :max="100"
                style="width: 150px"
              />
              <el-text size="small" type="info" style="margin-left: 12px">
                每N轮保存一次，-1表示只保存最佳和最后
              </el-text>
            </el-form-item>

            <el-form-item>
              <el-button type="primary" :loading="creating" @click="createJob">开始训练</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>

      <!-- Jobs List -->
      <el-col :span="14">
        <el-card shadow="never">
          <template #header>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span>训练任务</span>
              <el-button size="small" :icon="Refresh" @click="fetchJobs">刷新</el-button>
            </div>
          </template>

          <el-empty v-if="!jobs.length" description="暂无训练任务" />

          <div v-else>
            <el-card
              v-for="job in jobs"
              :key="job.id"
              class="job-card"
              :class="job.status"
              shadow="never"
              @click="$router.push(`/training/${job.id}`)"
            >
              <div class="job-header">
                <div>
                  <el-tag :type="statusType(job.status)" size="small">{{ statusText(job.status) }}</el-tag>
                  <span class="job-name">{{ job.name }}</span>
                </div>
                <span class="job-model">{{ job.model_name }}</span>
              </div>

              <el-progress
                v-if="job.status === 'running'"
                :percentage="Math.round(job.current_epoch / job.epochs * 100)"
                :striped="true"
                :striped-flow="true"
              />
              <div v-if="job.status === 'running'" class="epoch-info">
                Epoch {{ job.current_epoch }} / {{ job.epochs }}
              </div>

              <div v-if="job.best_map50 !== null && job.best_map50 !== undefined" class="metrics">
                <span>mAP50: <strong>{{ (job.best_map50 * 100).toFixed(1) }}%</strong></span>
                <span v-if="job.best_map50_95">mAP50-95: <strong>{{ (job.best_map50_95 * 100).toFixed(1) }}%</strong></span>
              </div>

              <div class="job-footer">
                <span class="job-time">{{ formatDate(job.created_at) }}</span>
                <div v-if="job.status === 'running' || job.status === 'pending'" class="job-actions">
                  <el-button
                    link type="warning" size="small"
                    @click.stop="stopJob(job.id)"
                    title="立即停止训练并保存当前最佳模型"
                  >结束训练</el-button>
                  <el-button
                    link type="danger" size="small"
                    @click.stop="cancelJob(job.id)"
                    title="取消训练，不保存模型"
                  >取消</el-button>
                </div>
              </div>
            </el-card>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { trainingApi } from '@/api'
import { useTrainingStore } from '@/stores/training'
import { useDatasetStore } from '@/stores/dataset'
import { useProjectStore } from '@/stores/project'
import { storeToRefs } from 'pinia'
import { useRouter } from 'vue-router'

const router = useRouter()
const trainingStore = useTrainingStore()
const datasetStore = useDatasetStore()
const projectStore = useProjectStore()
const { jobs } = storeToRefs(trainingStore)
const { datasets } = storeToRefs(datasetStore)
const { hasProject, projectId } = storeToRefs(projectStore)

const formRef = ref()
const creating = ref(false)
const availableModels = ref([])
const datasetClasses = ref([])
const selectedDatasetInfo = ref(null)

const form = ref({
  name: '选择数据集和模型后自动生成',
  dataset_id: '',
  model_name: 'yolo11n.pt',
  epochs: 100,
  batch_size: 16,
  img_size: 640,
  learning_rate: 0.01,
  val_split: 0.2,
  device: 'auto',

  // 使用增强数据
  use_augmented_data: true,

  // 继续训练
  resume_training: false,
  base_model_id: '',

  // 类别增强
  use_class_enhancement: false,
  focus_classes: [],

  // 早停和保存策略
  patience: 50,
  save_period: -1,
})

const rules = {
  name: [{ required: true, message: '请输入任务名称' }],
  dataset_id: [{ required: true, message: '请选择数据集' }],
  base_model_id: [{
    required: false,
    validator: (rule, value, callback) => {
      if (form.value.resume_training && !value) {
        callback(new Error('请选择要继续训练的模型'))
      } else {
        callback()
      }
    }
  }],
}

const yolo11Models = ['yolo11n.pt', 'yolo11s.pt', 'yolo11m.pt', 'yolo11l.pt', 'yolo11x.pt']
const yolov8Models = ['yolov8n.pt', 'yolov8s.pt', 'yolov8m.pt', 'yolov8l.pt', 'yolov8x.pt']

let refreshTimer = null

const statusType = (s) => ({ pending: 'info', running: 'warning', completed: 'success', failed: 'danger', cancelled: '' })[s] || ''
const statusText = (s) => ({ pending: '等待', running: '训练中', completed: '完成', failed: '失败', cancelled: '已取消' })[s] || s
const formatDate = (d) => d ? new Date(d).toLocaleString('zh-CN', { hour12: false }) : '-'

onMounted(async () => {
  await Promise.all([
    fetchJobs(),
    datasetStore.fetchDatasets(),
    fetchAvailableModels(),
  ])
  refreshTimer = setInterval(() => {
    if (jobs.value.some((j) => j.status === 'running' || j.status === 'pending')) {
      fetchJobs()
    }
  }, 5000)
})

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
})

// 监听项目变化，刷新数据集和模型列表
watch(projectId, () => {
  datasetStore.fetchDatasets()
  fetchAvailableModels()
  fetchJobs()
  form.value.dataset_id = ''
  form.value.base_model_id = ''
})

// 监听数据集变化，加载类别列表
watch(() => form.value.dataset_id, () => {
  loadDatasetClasses()
  updateJobName()
  loadDatasetInfo()
})

// 监听模型名称变化，更新任务名称
watch(() => form.value.model_name, () => {
  updateJobName()
})

// 自动生成任务名称
function updateJobName() {
  if (!form.value.dataset_id || !form.value.model_name) return

  // 获取数据集名称
  const dataset = datasets.value.find(d => d.id === form.value.dataset_id)
  let datasetName = dataset ? dataset.name : '未知数据集'

  // 数据集名称过长时截断
  if (datasetName.length > 15) {
    datasetName = datasetName.substring(0, 15) + '...'
  }

  // 获取模型简称（去掉.pt后缀）
  const modelName = form.value.model_name.replace('.pt', '')

  // 获取当前时间
  const now = new Date()
  const dateStr = `${(now.getMonth() + 1).toString().padStart(2, '0')}${now.getDate().toString().padStart(2, '0')}`
  const timeStr = `${now.getHours().toString().padStart(2, '0')}${now.getMinutes().toString().padStart(2, '0')}`

  // 是否继续训练
  const prefix = form.value.resume_training ? '续训_' : ''

  // 生成任务名称：[续训_]数据集_模型_日期时间
  form.value.name = `${prefix}${datasetName}_${modelName}_${dateStr}_${timeStr}`
}

async function fetchJobs() {
  await trainingStore.fetchJobs()
}

async function fetchAvailableModels() {
  try {
    const params = {}
    if (projectId.value) {
      params.project_id = projectId.value
    }
    const res = await trainingApi.listModels(params)
    availableModels.value = res.models || res.items || []
  } catch (error) {
    console.error('Failed to fetch models:', error)
  }
}

async function loadDatasetClasses() {
  if (!form.value.dataset_id) {
    datasetClasses.value = []
    return
  }

  try {
    const dataset = datasets.value.find(d => d.id === form.value.dataset_id)
    if (dataset && dataset.classes) {
      datasetClasses.value = dataset.classes
    } else {
      datasetClasses.value = []
    }
  } catch (error) {
    console.error('Failed to load dataset classes:', error)
    datasetClasses.value = []
  }
}

async function loadDatasetInfo() {
  if (!form.value.dataset_id) {
    selectedDatasetInfo.value = null
    return
  }

  try {
    const { datasetApi } = await import('@/api')
    const stats = await datasetApi.getStats(form.value.dataset_id)

    selectedDatasetInfo.value = {
      image_count: stats.total_images,
      original_count: stats.original_count,
      augmented_count: stats.augmented_count,
      annotated_image_count: stats.annotated_image_count,
      original_annotated_count: stats.original_annotated_count,
      augmented_annotated_count: stats.augmented_annotated_count,
      unlabeled_augmented_count: stats.augmented_unannotated_count,
    }
  } catch (error) {
    console.error('Failed to load dataset info:', error)
    selectedDatasetInfo.value = null
  }
}

function goToAnnotation() {
  router.push('/annotation')
}

function onResumeTrainingChange(value) {
  if (value) {
    // 启用继续训练时，建议减少训练轮数
    if (form.value.epochs > 50) {
      ElMessage.info('继续训练建议减少训练轮数（已自动调整为50轮）')
      form.value.epochs = 50
    }
    // 加载可用模型列表
    fetchAvailableModels()
  } else {
    form.value.base_model_id = ''
  }
  // 更新任务名称
  updateJobName()
}

async function createJob() {
  await formRef.value.validate()
  creating.value = true
  try {
    const job = await trainingStore.createJob(form.value)
    router.push(`/training/${job.id}`)
  } catch (error) {
    // Error message is already shown by the API handler
    // Just ensure creating flag is reset
  } finally {
    creating.value = false
  }
}

async function cancelJob(id) {
  await trainingStore.cancelJob(id)
}

async function stopJob(id) {
  await trainingStore.stopJob(id)
}
</script>

<style scoped>
.hint { margin-left: 8px; color: #909399; font-size: 12px; }

.job-card {
  margin-bottom: 12px;
  cursor: pointer;
  border-left: 3px solid #dcdfe6;
  transition: box-shadow 0.2s;
}
.job-card:hover { box-shadow: 0 2px 12px rgba(0,0,0,0.1); }
.job-card.running { border-left-color: #e6a23c; }
.job-card.completed { border-left-color: #67c23a; }
.job-card.failed { border-left-color: #f56c6c; }

.job-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.job-name { margin-left: 8px; font-weight: 500; font-size: 14px; }
.job-model { color: #909399; font-size: 12px; }
.epoch-info { font-size: 12px; color: #909399; margin-top: 4px; }
.metrics { display: flex; gap: 20px; font-size: 13px; color: #606266; margin-top: 8px; }
.job-footer { display: flex; justify-content: space-between; align-items: center; margin-top: 8px; }
.job-time { font-size: 12px; color: #c0c4cc; }
.job-actions { display: flex; gap: 8px; }
</style>
