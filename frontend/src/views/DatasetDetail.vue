<template>
  <div>
    <!-- Breadcrumb Navigation -->
    <el-breadcrumb separator="/" style="margin-bottom: 16px">
      <el-breadcrumb-item :to="{ path: '/projects' }">项目管理</el-breadcrumb-item>
      <el-breadcrumb-item v-if="dataset?.project_id" :to="{ path: `/projects/${dataset.project_id}` }">
        项目详情
      </el-breadcrumb-item>
      <el-breadcrumb-item>{{ dataset?.name || '数据集详情' }}</el-breadcrumb-item>
    </el-breadcrumb>

    <el-page-header @back="goBack" class="page-header">
      <template #content>
        <span style="font-weight:600">{{ dataset?.name }}</span>
      </template>
      <template #extra>
        <el-space>
          <el-button :icon="Download" @click="$router.push(`/collect?dataset=${id}`)">采集图片</el-button>
          <el-button type="primary" :icon="MagicStick" @click="showAugDialog = true">数据增强</el-button>
          <el-button type="success" :icon="Cpu" @click="showTrainDialog = true">开始训练</el-button>
        </el-space>
      </template>
    </el-page-header>

    <el-row :gutter="16" style="margin-top: 20px">
      <!-- Dataset info -->
      <el-col :span="6">
        <el-card shadow="never">
          <div class="info-item"><span>图片总数</span><strong>{{ dataset?.image_count }}</strong></div>
          <div class="info-item"><span>标注总数</span><strong>{{ dataset?.annotation_count }}</strong></div>
          <div class="info-item"><span>状态</span>
            <el-tag :type="statusType(dataset?.status)" size="small">{{ dataset?.status }}</el-tag>
          </div>
          <div class="info-item" v-if="dataset?.classes?.length">
            <span>类别</span>
            <div>
              <el-tag v-for="cls in dataset.classes" :key="cls" size="small" style="margin: 2px">{{ cls }}</el-tag>
            </div>
          </div>
        </el-card>

        <!-- 标注快捷入口 -->
        <el-card shadow="never" style="margin-top: 16px">
          <template #header>
            <span style="font-weight: 500">快捷操作</span>
          </template>
          <el-button type="primary" @click="activeTab = 'annotation'" style="width: 100%; margin-bottom: 8px">
            <el-icon style="margin-right: 4px"><Edit /></el-icon>
            开始标注
          </el-button>
          <el-button @click="activeTab = 'augmentation'" style="width: 100%">
            <el-icon style="margin-right: 4px"><Operation /></el-icon>
            管理增强数据
          </el-button>
        </el-card>
      </el-col>

      <!-- Annotation and Augmentation Management Tabs -->
      <el-col :span="18">
        <el-card shadow="never">
          <el-tabs v-model="activeTab">
            <el-tab-pane label="📝 标注管理" name="annotation">
              <AnnotationView
                v-if="dataset && images.length > 0"
                :datasetId="id"
                :images="images"
                :classes="dataset?.classes || []"
                :imageUrlFunc="imageUrl"
                @annotationsSaved="onAnnotationsSaved"
              />
              <el-empty v-else description="请先添加图片">
                <el-button type="primary" @click="$router.push(`/collect?dataset=${id}`)">立即采集</el-button>
              </el-empty>
            </el-tab-pane>

            <el-tab-pane label="🎨 增强管理" name="augmentation">
              <AugmentationManager
                v-if="images.length > 0"
                :datasetId="id"
                :images="images"
                :imageUrlFunc="imageUrl"
                @update="loadImages"
              />
              <el-empty v-else description="暂无数据" />
            </el-tab-pane>

            <el-tab-pane label="🖼️ 图片列表" name="images">
              <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
                <span>图片总数: {{ imageTotal }}</span>
                <el-checkbox v-model="showAugmented" @change="loadImages">显示增强图片</el-checkbox>
              </div>

              <div v-loading="loading">
                <el-empty v-if="!images.length" description="暂无图片，请先采集数据" />
                <div v-else class="image-grid">
                  <div
                    v-for="img in images"
                    :key="img.id"
                    class="image-card"
                    :class="{ augmented: img.is_augmented }"
                  >
                    <el-image
                      :src="imageUrl(img.id, true)"
                      fit="cover"
                      loading="lazy"
                      class="image-thumb"
                    >
                      <template #error>
                        <div class="image-error"><el-icon><Picture /></el-icon></div>
                      </template>
                    </el-image>
                    <div class="image-info">
                      <span class="image-name" :title="img.original_filename">{{ img.original_filename }}</span>
                      <el-badge :value="img.annotations?.length || 0" type="info" class="ann-badge" />
                    </div>
                    <div class="image-actions">
                      <el-tag v-if="img.is_augmented" type="warning" size="small">增强</el-tag>
                      <el-popconfirm title="确认删除?" @confirm="deleteImage(img.id)">
                        <template #reference>
                          <el-button circle size="small" :icon="Delete" type="danger" />
                        </template>
                      </el-popconfirm>
                    </div>
                  </div>
                </div>

                <div style="text-align:center;margin-top:16px" v-if="imageTotal > images.length">
                  <el-button @click="loadMore" :loading="loadingMore">加载更多</el-button>
                </div>
              </div>
            </el-tab-pane>
          </el-tabs>
        </el-card>
      </el-col>
    </el-row>

    <!-- Augmentation quick dialog -->
    <el-dialog v-model="showAugDialog" title="快速数据增强" width="400px">
      <el-form label-width="100px">
        <el-form-item label="增强倍数">
          <el-input-number v-model="augMultiplier" :min="1" :max="20" />
          <span style="margin-left:8px;color:#909399">每张图片生成 {{ augMultiplier }} 张增强图片</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAugDialog = false">取消</el-button>
        <el-button type="primary" :loading="augLoading" @click="startAugmentation">开始增强</el-button>
      </template>
    </el-dialog>

    <!-- Train quick dialog -->
    <el-dialog v-model="showTrainDialog" title="快速启动训练" width="500px">
      <el-form :model="trainForm" label-width="100px">
        <el-form-item label="任务名称">
          <el-input v-model="trainForm.name" />
        </el-form-item>
        <el-form-item label="基础模型">
          <el-select v-model="trainForm.model_name" style="width:100%">
            <el-option v-for="m in availableModels" :key="m" :label="m" :value="m" />
          </el-select>
        </el-form-item>
        <el-form-item label="训练轮数">
          <el-input-number v-model="trainForm.epochs" :min="1" :max="1000" />
        </el-form-item>
        <el-form-item label="批大小">
          <el-input-number v-model="trainForm.batch_size" :min="1" :max="512" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showTrainDialog = false">取消</el-button>
        <el-button type="primary" :loading="trainLoading" @click="startTraining">开始训练</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Delete, Download, MagicStick, Cpu, Picture, Edit, Operation } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { datasetApi, augmentationApi, trainingApi } from '@/api'
import { useDatasetStore } from '@/stores/dataset'
import { storeToRefs } from 'pinia'
import AnnotationView from '@/components/annotation/AnnotationView.vue'
import AugmentationManager from '@/components/augmentation/AugmentationManager.vue'

const route = useRoute()
const router = useRouter()
const id = route.params.id
const store = useDatasetStore()
const { currentDataset: dataset, images, imageTotal, loading } = storeToRefs(store)

const activeTab = ref('annotation')
const showAugmented = ref(false)
const loadingMore = ref(false)
const currentPage = ref(1)
const showAugDialog = ref(false)
const augMultiplier = ref(3)
const augLoading = ref(false)
const showTrainDialog = ref(false)
const trainLoading = ref(false)
const availableModels = ref([])

const trainForm = ref({
  name: `训练_${new Date().toLocaleDateString('zh-CN')}`,
  model_name: 'yolo11n.pt',
  epochs: 100,
  batch_size: 16,
  img_size: 640,
  learning_rate: 0.01,
  val_split: 0.2,
  device: 'auto',
})

const imageUrl = (imageId, thumb = false) => datasetApi.imageUrl(imageId, thumb)
const statusType = (s) => ({ active: 'success', ready: 'success', error: 'danger' })[s] || 'info'

onMounted(async () => {
  await Promise.all([
    store.fetchDataset(id),
    loadImages(),
  ])
  const modRes = await trainingApi.availableModels()
  availableModels.value = modRes.models
  trainForm.value.name = `${dataset.value?.name}_训练_${new Date().toLocaleDateString('zh-CN')}`
})

function goBack() {
  // 如果数据集有 project_id，返回到项目详情页
  if (dataset.value?.project_id) {
    router.push(`/projects/${dataset.value.project_id}`)
  } else {
    // 否则返回到项目列表
    router.push('/projects')
  }
}

async function loadImages() {
  currentPage.value = 1
  await store.fetchImages(id, { page: 1, augmented_only: showAugmented.value })
}

async function loadMore() {
  loadingMore.value = true
  currentPage.value++
  try {
    const res = await datasetApi.listImages(id, {
      page: currentPage.value,
      page_size: 50,
      augmented_only: showAugmented.value,
    })
    images.value.push(...res.items)
  } finally {
    loadingMore.value = false
  }
}

async function deleteImage(imageId) {
  await datasetApi.deleteImage(id, imageId)
  images.value = images.value.filter((i) => i.id !== imageId)
  imageTotal.value--
  ElMessage.success('图片已删除')
}

function onAnnotationsSaved(data) {
  ElMessage.success('标注已保存')
  // 重新加载图片以更新标注数量
  loadImages()
}

async function startAugmentation() {
  augLoading.value = true
  try {
    const job = await augmentationApi.createJob({
      dataset_id: id,
      multiplier: augMultiplier.value,
    })
    showAugDialog.value = false
    ElMessage.success('数据增强任务已创建')
    router.push('/augmentation')
  } finally {
    augLoading.value = false
  }
}

async function startTraining() {
  trainLoading.value = true
  try {
    const job = await trainingApi.createJob({ ...trainForm.value, dataset_id: id })
    showTrainDialog.value = false
    ElMessage.success('训练任务已启动')
    router.push(`/training/${job.id}`)
  } finally {
    trainLoading.value = false
  }
}
</script>

<style scoped>
.info-item {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 10px 0;
  border-bottom: 1px solid #f5f5f5;
  gap: 8px;
}
.info-item span { color: #909399; font-size: 13px; flex-shrink: 0; }
.info-item strong { font-weight: 600; }

.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 12px;
}

.image-card {
  border: 1px solid #ebeef5;
  border-radius: 8px;
  overflow: hidden;
  transition: box-shadow 0.2s;
  background: #fff;
}
.image-card:hover { box-shadow: 0 2px 12px rgba(0,0,0,0.1); }
.image-card.augmented { border-color: #e6a23c44; }

.image-thumb {
  width: 100%;
  height: 120px;
  display: block;
}

.image-error {
  width: 100%;
  height: 120px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f5f7fa;
  color: #c0c4cc;
}

.image-info {
  padding: 6px 8px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
}

.image-name {
  font-size: 11px;
  color: #606266;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.image-actions {
  padding: 4px 8px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-top: 1px solid #f5f5f5;
}
</style>
