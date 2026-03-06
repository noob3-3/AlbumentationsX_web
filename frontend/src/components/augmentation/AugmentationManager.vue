<template>
  <div class="augmentation-manager">
    <el-card shadow="never">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <span>增强数据管理</span>
          <el-space>
            <el-statistic title="增强图片数" :value="augmentedImagesCount" />
            <el-button type="danger" size="small" :disabled="augmentedImagesCount === 0" @click="deleteAllAugmented">
              删除所有增强
            </el-button>
          </el-space>
        </div>
      </template>

      <div v-if="augmentedImages.length === 0" style="padding: 20px; text-align: center; color: #909399">
        没有增强数据
      </div>

      <el-table v-else :data="augmentedImages" size="small">
        <el-table-column type="index" width="50" label="序号" />

        <el-table-column label="原始图片" width="200">
          <template #default="{ row }">
            <div style="display: flex; align-items: center; gap: 8px">
              <el-image :src="imageUrl(row.original_image_id, true)" style="width: 40px; height: 40px; border-radius: 4px" />
              <span style="font-size: 12px; max-width: 140px; overflow: hidden; text-overflow: ellipsis">
                {{ row.original_filename }}
              </span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="增强类型" width="100">
          <template #default="{ row }">
            <el-tag type="info" size="small">{{ row.augmentation_type }}</el-tag>
          </template>
        </el-table-column>

        <el-table-column label="大小" width="80" align="center">
          <template #default="{ row }">
            {{ formatFileSize(row.file_size) }}
          </template>
        </el-table-column>

        <el-table-column label="创建时间" width="160">
          <template #default="{ row }">
            {{ formatDate(row.created_at) }}
          </template>
        </el-table-column>

        <el-table-column label="操作" width="100" align="center" fixed="right">
          <template #default="{ row }">
            <el-popconfirm title="确认删除此增强图片?" @confirm="deleteAugmented(row.id)">
              <template #reference>
                <el-button link type="danger" size="small" icon="Delete">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>

      <!-- Statistics -->
      <el-divider v-if="augmentedImages.length > 0" />

      <el-row v-if="augmentedImages.length > 0" :gutter="16">
        <el-col :span="6">
          <div class="stat-box">
            <div class="stat-label">增强图片总数</div>
            <div class="stat-value">{{ augmentedImagesCount }}</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-box">
            <div class="stat-label">占原图比例</div>
            <div class="stat-value">{{ augmentedRatio }}%</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-box">
            <div class="stat-label">占用空间</div>
            <div class="stat-value">{{ totalAugmentedSize }}</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-box">
            <div class="stat-label">平均增强倍数</div>
            <div class="stat-value">{{ avgAugmentationFactor.toFixed(1) }}x</div>
          </div>
        </el-col>
      </el-row>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  datasetId: String,
  images: {
    type: Array,
    default: () => [],
  },
  imageUrlFunc: Function,
})

const emit = defineEmits(['update'])

const augmentedImages = ref([])

const augmentedImagesCount = computed(() => augmentedImages.value.length)

const augmentedRatio = computed(() => {
  if (props.images.length === 0) return 0
  const total = props.images.length
  return ((augmentedImagesCount.value / total) * 100).toFixed(1)
})

const totalAugmentedSize = computed(() => {
  const bytes = augmentedImages.value.reduce((sum, img) => sum + (img.file_size || 0), 0)
  return formatFileSize(bytes)
})

const avgAugmentationFactor = computed(() => {
  if (augmentedImagesCount.value === 0) return 0
  const originalCount = props.images.filter((img) => !img.is_augmented).length
  if (originalCount === 0) return 0
  return augmentedImagesCount.value / originalCount
})

onMounted(() => {
  // Filter augmented images from the images list
  if (props.images) {
    augmentedImages.value = props.images.filter((img) => img.is_augmented)
  }
})

function imageUrl(imageId, thumbnail = false) {
  if (props.imageUrlFunc) {
    return props.imageUrlFunc(imageId, thumbnail)
  }
  return `/api/v1/datasets/files/image/${imageId}${thumbnail ? '?thumbnail=true' : ''}`
}

function formatFileSize(bytes) {
  if (!bytes) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

function formatDate(date) {
  return new Date(date).toLocaleString('zh-CN', { hour12: false })
}

async function deleteAugmented(imageId) {
  try {
    const response = await fetch(`/api/v1/datasets/${props.datasetId}/images/${imageId}`, {
      method: 'DELETE',
    })

    if (!response.ok) {
      throw new Error('删除失败')
    }

    const index = augmentedImages.value.findIndex((img) => img.id === imageId)
    if (index > -1) {
      augmentedImages.value.splice(index, 1)
      emit('update')
      ElMessage.success('增强图片已删除')
    }
  } catch (error) {
    ElMessage.error('删除失败：' + error.message)
  }
}

function deleteAllAugmented() {
  // 批量删除所有增强图片
  augmentedImages.value.forEach((img) => {
    deleteAugmented(img.id)
  })
}
</script>

<style scoped>
.augmentation-manager {
  margin-top: 20px;
}

.stat-box {
  background: #f5f7fa;
  padding: 16px;
  border-radius: 4px;
  text-align: center;
}

.stat-label {
  color: #909399;
  font-size: 12px;
  margin-bottom: 8px;
}

.stat-value {
  font-size: 20px;
  font-weight: bold;
  color: #303133;
}
</style>

