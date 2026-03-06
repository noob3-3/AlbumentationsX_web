<template>
  <div class="augmentation-page">
    <div class="page-header">
      <h2>数据增强配置</h2>
      <p>基于 Albumentations 的专业图像增强工具，适用于目标检测和图像分类任务</p>
    </div>

    <!-- Project Warning -->
    <el-alert
      v-if="!hasProject"
      type="warning"
      title="请先在页面顶部选择一个项目"
      description="选择项目后，下方数据集列表将只显示该项目的数据集"
      :closable="false"
      style="margin-bottom: 16px"
      show-icon
    />

    <el-row :gutter="20">
      <!-- Left Panel: Configuration -->
      <el-col :span="15">
        <el-card shadow="never">
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center">
              <span>创建增强任务</span>
              <el-button-group size="small">
                <el-button :type="configMode === 'preset' ? 'primary' : ''" @click="configMode = 'preset'">
                  预设配置
                </el-button>
                <el-button :type="configMode === 'custom' ? 'primary' : ''" @click="configMode = 'custom'">
                  自定义
                </el-button>
              </el-button-group>
            </div>
          </template>

          <el-form :model="form" label-width="100px" label-position="left">
            <!-- Dataset Selection -->
            <el-form-item label="源数据集" required>
              <el-select
                v-model="form.dataset_id"
                placeholder="选择数据集"
                style="width: 100%"
                :disabled="!hasProject"
              >
                <el-option
                  v-for="d in datasets"
                  :key="d.id"
                  :label="`${d.name} (${d.image_count}张)`"
                  :value="d.id"
                />
              </el-select>
              <div v-if="!hasProject" class="hint">请先选择项目</div>
              <div v-else-if="datasets.length === 0" class="hint">当前项目暂无数据集</div>
            </el-form-item>

            <!-- Multiplier -->
            <el-form-item label="增强倍数">
              <el-input-number v-model="form.multiplier" :min="1" :max="20" style="width: 150px" />
              <span class="hint" style="margin-left: 12px">
                每张原始图片生成 {{ form.multiplier }} 张增强图片
              </span>
            </el-form-item>

            <el-divider />

            <!-- Preset Mode -->
            <div v-if="configMode === 'preset'">
              <el-form-item label="预设方案">
                <el-radio-group v-model="selectedPreset" @change="onPresetChange">
                  <el-space direction="vertical" style="width: 100%">
                    <el-radio
                      v-for="(config, key) in presetConfigs"
                      :key="key"
                      :value="key"
                      style="width: 100%; margin: 0"
                    >
                      <div class="preset-option">
                        <div class="preset-title">{{ config.name }}</div>
                        <div class="preset-desc">{{ config.description }}</div>
                        <div class="preset-transforms">
                          包含 {{ config.transforms.length }} 种增强方式
                        </div>
                      </div>
                    </el-radio>
                  </el-space>
                </el-radio-group>
              </el-form-item>

              <!-- Preview Preset Transforms -->
              <el-collapse v-if="selectedPreset" style="margin-top: 16px">
                <el-collapse-item title="查看包含的增强方式" name="1">
                  <div class="transform-list">
                    <el-tag
                      v-for="t in presetConfigs[selectedPreset].transforms"
                      :key="t.name"
                      size="small"
                      style="margin: 4px"
                    >
                      {{ getTransformLabel(t.name) }}
                    </el-tag>
                  </div>
                </el-collapse-item>
              </el-collapse>
            </div>

            <!-- Custom Mode -->
            <div v-if="configMode === 'custom'" class="custom-config">
              <el-tabs v-model="activeCategory" type="border-card">
                <el-tab-pane
                  v-for="(categoryName, categoryKey) in categories"
                  :key="categoryKey"
                  :label="categoryName"
                  :name="categoryKey"
                >
                  <div class="transform-category">
                    <el-space wrap>
                      <div
                        v-for="transformName in transformsByCategory[categoryKey]"
                        :key="transformName"
                        class="transform-card"
                        :class="{ active: isTransformSelected(transformName) }"
                      >
                        <div class="transform-card-header">
                          <el-checkbox
                            :model-value="isTransformSelected(transformName)"
                            @change="(val) => toggleTransform(transformName, val)"
                          />
                          <span
                            class="transform-card-title"
                            @click="toggleTransform(transformName)"
                            style="cursor: pointer; flex: 1"
                          >
                            {{ transformsInfo[transformName]?.name_zh || transformName }}
                          </span>
                        </div>
                        <div class="transform-card-desc">
                          {{ transformsInfo[transformName]?.description || '暂无描述' }}
                        </div>

                        <!-- Settings Button -->
                        <el-button
                          v-if="isTransformSelected(transformName) && transformsInfo[transformName]?.params"
                          link
                          type="primary"
                          size="small"
                          style="margin-top: 8px"
                          @click.stop="openTransformSettings(transformName)"
                        >
                          <el-icon><Setting /></el-icon>
                          调整参数
                        </el-button>
                      </div>
                    </el-space>
                  </div>
                </el-tab-pane>
              </el-tabs>

              <el-alert
                v-if="selectedTransforms.length === 0"
                type="warning"
                title="请至少选择一种增强方式"
                :closable="false"
                style="margin-top: 16px"
                show-icon
              />
            </div>

            <el-divider />

            <!-- Action Buttons -->
            <el-form-item>
              <el-space>
                <el-button
                  type="primary"
                  :loading="creating"
                  :disabled="!form.dataset_id || (configMode === 'custom' && selectedTransforms.length === 0)"
                  @click="createJob"
                >
                  <el-icon><Promotion /></el-icon>
                  创建增强任务
                </el-button>
                <el-button @click="resetForm">
                  <el-icon><RefreshLeft /></el-icon>
                  重置
                </el-button>
              </el-space>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>

      <!-- Right Panel: Jobs List -->
      <el-col :span="9">
        <el-card shadow="never">
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center">
              <span>增强任务列表</span>
              <el-button size="small" :icon="Refresh" @click="fetchJobs">刷新</el-button>
            </div>
          </template>

          <el-scrollbar height="700px">
            <el-empty v-if="!jobs.length" description="暂无增强任务" />

            <div v-else>
              <el-card
                v-for="job in jobs"
                :key="job.id"
                class="job-card"
                shadow="never"
                :class="job.status"
              >
                <div class="job-header">
                  <div>
                    <el-tag :type="statusType(job.status)" size="small">
                      {{ statusText(job.status) }}
                    </el-tag>
                    <span class="job-id">{{ job.id.slice(0, 8) }}...</span>
                  </div>
                  <span class="job-time">{{ formatDate(job.created_at) }}</span>
                </div>

                <div class="job-meta">
                  <span>倍数: <strong>×{{ job.multiplier }}</strong></span>
                  <span>目标: <strong>{{ job.total_images }}</strong> 张</span>
                  <span>已完成: <strong>{{ job.processed_images }}</strong> 张</span>
                </div>

                <el-progress
                  v-if="job.status === 'running'"
                  :percentage="Math.round((job.processed_images / Math.max(job.total_images, 1)) * 100)"
                  :striped="true"
                  :striped-flow="true"
                  :duration="5"
                />

                <div v-if="job.status === 'completed' && job.output_dataset_id" style="margin-top: 8px">
                  <el-button
                    link
                    type="primary"
                    size="small"
                    @click="$router.push(`/datasets/${job.output_dataset_id}`)"
                  >
                    查看输出数据集 →
                  </el-button>
                </div>

                <div v-if="job.error_message" class="error-msg">{{ job.error_message }}</div>
              </el-card>
            </div>
          </el-scrollbar>
        </el-card>
      </el-col>
    </el-row>

    <!-- Transform Settings Dialog -->
    <el-dialog
      v-model="settingsDialogVisible"
      :title="`${currentTransform ? transformsInfo[currentTransform]?.name_zh : ''} - 参数设置`"
      width="500px"
    >
      <div v-if="currentTransform && transformsInfo[currentTransform]">
        <el-form label-width="120px">
          <el-form-item
            v-for="(paramDef, paramName) in transformsInfo[currentTransform].params"
            :key="paramName"
            :label="paramDef.label"
          >
            <!-- Float parameter -->
            <el-input-number
              v-if="paramDef.type === 'float'"
              v-model="transformParams[currentTransform][paramName]"
              :min="paramDef.min"
              :max="paramDef.max"
              :step="0.1"
              :precision="2"
              style="width: 200px"
            />

            <!-- Integer parameter -->
            <el-input-number
              v-if="paramDef.type === 'int'"
              v-model="transformParams[currentTransform][paramName]"
              :min="paramDef.min"
              :max="paramDef.max"
              :step="1"
              style="width: 200px"
            />

            <!-- Range parameter -->
            <div v-if="paramDef.type === 'range'" style="display: flex; gap: 8px; align-items: center">
              <el-input-number
                v-model="transformParams[currentTransform][paramName][0]"
                :min="paramDef.min"
                :max="paramDef.max"
                :step="0.1"
                style="width: 120px"
              />
              <span>至</span>
              <el-input-number
                v-model="transformParams[currentTransform][paramName][1]"
                :min="paramDef.min"
                :max="paramDef.max"
                :step="0.1"
                style="width: 120px"
              />
            </div>
          </el-form-item>
        </el-form>
      </div>
      <template #footer>
        <el-button @click="settingsDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveTransformSettings">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { Refresh, Setting, Promotion, RefreshLeft } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { augmentationApi } from '@/api'
import { useDatasetStore } from '@/stores/dataset'
import { useProjectStore } from '@/stores/project'
import { storeToRefs } from 'pinia'

const store = useDatasetStore()
const projectStore = useProjectStore()
const { datasets } = storeToRefs(store)
const { hasProject, projectId } = storeToRefs(projectStore)

// Form data
const form = ref({ dataset_id: '', multiplier: 3, config: null })
const configMode = ref('preset') // 'preset' or 'custom'
const selectedPreset = ref('medium')

// Transform data
const transformsInfo = ref({})
const categories = ref({})
const transformsByCategory = ref({})
const presetConfigs = ref({})

// Custom mode
const activeCategory = ref('')
const selectedTransforms = ref([])
const transformParams = ref({}) // Store custom parameters for each transform

// Settings dialog
const settingsDialogVisible = ref(false)
const currentTransform = ref(null)

// Jobs
const jobs = ref([])
const creating = ref(false)

let refreshTimer = null

const statusType = (s) => ({ pending: 'info', running: 'warning', completed: 'success', failed: 'danger' })[s] || ''
const statusText = (s) => ({ pending: '等待中', running: '增强中', completed: '已完成', failed: '失败' })[s] || s
const formatDate = (d) => (d ? new Date(d).toLocaleString('zh-CN', { hour12: false }) : '-')

const getTransformLabel = (name) => {
  return transformsInfo.value[name]?.name_zh || name
}

const isTransformSelected = (name) => {
  return selectedTransforms.value.includes(name)
}

const toggleTransform = (name, val) => {
  // If val is explicitly provided (from checkbox), use it; otherwise toggle
  const shouldAdd = val !== undefined ? val : !isTransformSelected(name)

  const index = selectedTransforms.value.indexOf(name)

  if (shouldAdd && index === -1) {
    // Add transform
    selectedTransforms.value.push(name)
    // Initialize default params
    if (!transformParams.value[name]) {
      initializeTransformParams(name)
    }
  } else if (!shouldAdd && index > -1) {
    // Remove transform
    selectedTransforms.value.splice(index, 1)
  }
}

const initializeTransformParams = (transformName) => {
  const info = transformsInfo.value[transformName]
  if (!info || !info.params) return

  transformParams.value[transformName] = {}
  for (const [paramName, paramDef] of Object.entries(info.params)) {
    if (paramDef.type === 'range') {
      transformParams.value[transformName][paramName] = [...paramDef.default]
    } else {
      transformParams.value[transformName][paramName] = paramDef.default
    }
  }
}

const openTransformSettings = (transformName) => {
  currentTransform.value = transformName
  if (!transformParams.value[transformName]) {
    initializeTransformParams(transformName)
  }
  settingsDialogVisible.value = true
}

const saveTransformSettings = () => {
  settingsDialogVisible.value = false
  ElMessage.success('参数已保存')
}

const onPresetChange = () => {
  // Reset custom selections when preset changes
  selectedTransforms.value = []
}

const resetForm = () => {
  form.value = { dataset_id: '', multiplier: 3, config: null }
  selectedTransforms.value = []
  transformParams.value = {}
  selectedPreset.value = 'medium'
}

onMounted(async () => {
  await Promise.all([store.fetchDatasets(), fetchJobs(), fetchTransforms(), fetchPresets()])

  // Auto-refresh running jobs
  refreshTimer = setInterval(() => {
    if (jobs.value.some((j) => j.status === 'running' || j.status === 'pending')) {
      fetchJobs()
    }
  }, 3000)
})

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
})

watch(projectId, () => {
  store.fetchDatasets()
  form.value.dataset_id = ''
})

async function fetchJobs() {
  try {
    const res = await augmentationApi.listJobs()
    jobs.value = res.items
  } catch (error) {
    console.error('Failed to fetch jobs:', error)
  }
}

async function fetchTransforms() {
  try {
    const res = await augmentationApi.listTransforms()
    transformsInfo.value = res.transforms
    categories.value = res.categories
    transformsByCategory.value = res.by_category

    // Set first category as active
    const categoryKeys = Object.keys(categories.value)
    if (categoryKeys.length > 0) {
      activeCategory.value = categoryKeys[0]
    }
  } catch (error) {
    ElMessage.error('加载增强方式失败')
  }
}

async function fetchPresets() {
  try {
    const res = await augmentationApi.getRecommendedConfigs()
    presetConfigs.value = res.configs
  } catch (error) {
    ElMessage.error('加载预设配置失败')
  }
}

async function createJob() {
  if (!form.value.dataset_id) {
    ElMessage.warning('请选择数据集')
    return
  }

  creating.value = true
  try {
    let config = null

    if (configMode.value === 'preset') {
      // Use preset config
      config = {
        transforms: presetConfigs.value[selectedPreset.value].transforms,
      }
    } else {
      // Use custom config
      if (selectedTransforms.value.length === 0) {
        ElMessage.warning('请至少选择一种增强方式')
        creating.value = false
        return
      }

      config = {
        transforms: selectedTransforms.value.map((name) => {
          const params = transformParams.value[name] || {}

          // Handle Affine special case
          if (name === 'Affine' && params.translate_percent_x && params.translate_percent_y) {
            const finalParams = { ...params }
            finalParams.translate_percent = {
              x: params.translate_percent_x,
              y: params.translate_percent_y,
            }
            delete finalParams.translate_percent_x
            delete finalParams.translate_percent_y
            return { name, params: finalParams }
          }

          // Handle RandomResizedCrop size parameter
          if (name === 'RandomResizedCrop' && params.height && params.width) {
            const finalParams = { ...params }
            finalParams.size = [params.height, params.width]
            return { name, params: finalParams }
          }

          return { name, params }
        }),
      }
    }

    await augmentationApi.createJob({
      dataset_id: form.value.dataset_id,
      multiplier: form.value.multiplier,
      config,
    })

    ElMessage.success('增强任务已创建并开始运行')
    await fetchJobs()
  } catch (error) {
    ElMessage.error('创建任务失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    creating.value = false
  }
}
</script>

<style scoped>
.augmentation-page {
  padding: 0;
}

.hint {
  margin-left: 8px;
  color: #909399;
  font-size: 12px;
}

.preset-option {
  padding: 8px 0;
  white-space: normal;
  line-height: 1.5;
}

:deep(.el-radio) {
  height: auto !important;
  align-items: flex-start;
}

:deep(.el-radio__label) {
  white-space: normal;
  line-height: 1.5;
  overflow: visible;
}

.preset-title {
  font-weight: 600;
  font-size: 14px;
  color: #303133;
}

.preset-desc {
  font-size: 12px;
  color: #606266;
  margin-top: 4px;
}

.preset-transforms {
  font-size: 11px;
  color: #909399;
  margin-top: 4px;
}

.transform-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.custom-config {
  margin-top: 16px;
}

.transform-category {
  padding: 12px;
}

.transform-card {
  width: 240px;
  padding: 12px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.3s;
  background: #fff;
}

.transform-card:hover {
  border-color: #409eff;
  box-shadow: 0 2px 8px rgba(64, 158, 255, 0.2);
}

.transform-card.active {
  border-color: #409eff;
  background: #ecf5ff;
}

.transform-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.transform-card-title {
  font-weight: 600;
  font-size: 13px;
  color: #303133;
}

.transform-card-desc {
  font-size: 11px;
  color: #606266;
  line-height: 1.4;
  min-height: 32px;
}

.job-card {
  margin-bottom: 12px;
  border-left: 3px solid #dcdfe6;
}

.job-card.running {
  border-left-color: #e6a23c;
}

.job-card.completed {
  border-left-color: #67c23a;
}

.job-card.failed {
  border-left-color: #f56c6c;
}

.job-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.job-id {
  margin-left: 8px;
  color: #909399;
  font-size: 12px;
}

.job-time {
  color: #909399;
  font-size: 12px;
}

.job-meta {
  display: flex;
  gap: 16px;
  font-size: 13px;
  color: #606266;
  margin-bottom: 8px;
}

.error-msg {
  color: #f56c6c;
  font-size: 12px;
  margin-top: 6px;
}
</style>

