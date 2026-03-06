 <template>
  <el-dialog
    v-model="visible"
    title="批量替换类别"
    width="700px"
    @close="onClose"
  >
    <el-alert
      title="将数据集中所有标注的类别批量替换为自定义类别"
      type="info"
      :closable="false"
      show-icon
      style="margin-bottom: 16px"
    />

    <!-- 当前类别列表 -->
    <div v-if="currentClasses.length > 0" style="margin-bottom: 16px">
      <el-text type="info">当前数据集类别（共 {{ currentClasses.length }} 个）:</el-text>
      <div style="margin-top: 8px">
        <el-tag
          v-for="cls in currentClasses"
          :key="cls"
          style="margin-right: 8px; margin-bottom: 8px"
        >
          {{ cls }}
        </el-tag>
      </div>
    </div>

    <el-divider />

    <!-- 类别映射表格 -->
    <div style="margin-bottom: 16px">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px">
        <el-text style="font-weight: 500">类别映射规则</el-text>
        <el-button
          size="small"
          type="primary"
          @click="addMapping"
          icon="Plus"
        >
          添加映射
        </el-button>
      </div>

      <el-table
        :data="mappings"
        border
        style="width: 100%"
        max-height="400px"
      >
        <el-table-column label="序号" type="index" width="60" align="center" />

        <el-table-column label="原类别" width="200">
          <template #default="{ row, $index }">
            <el-select
              v-model="row.oldClass"
              placeholder="选择原类别"
              filterable
              allow-create
              style="width: 100%"
            >
              <el-option
                v-for="cls in currentClasses"
                :key="cls"
                :label="cls"
                :value="cls"
              />
            </el-select>
          </template>
        </el-table-column>

        <el-table-column label="" width="60" align="center">
          <template #default>
            <el-icon><Right /></el-icon>
          </template>
        </el-table-column>

        <el-table-column label="新类别" width="200">
          <template #default="{ row }">
            <el-input
              v-model="row.newClass"
              placeholder="输入新类别名称"
              clearable
            />
          </template>
        </el-table-column>

        <el-table-column label="操作" width="100" align="center">
          <template #default="{ $index }">
            <el-button
              type="danger"
              size="small"
              link
              @click="removeMapping($index)"
              icon="Delete"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 快捷预设 -->
      <div style="margin-top: 16px">
        <el-divider content-position="left">
          <el-text size="small">常用预设</el-text>
        </el-divider>
        <el-space wrap>
          <el-button size="small" @click="loadPreset('coco_to_chinese')">
            COCO英文 → 中文
          </el-button>
          <el-button size="small" @click="loadPreset('simplify')">
            简化类别名
          </el-button>
          <el-button size="small" @click="clearMappings">
            清空全部
          </el-button>
        </el-space>
      </div>
    </div>

    <!-- 预览 -->
    <el-alert
      v-if="mappings.length > 0"
      type="warning"
      :closable="false"
      show-icon
    >
      <template #title>
        <span style="font-size: 13px">
          将替换 <strong>{{ validMappingsCount }}</strong> 个类别映射，
          可能影响数据集中的 <strong>多个标注</strong>
        </span>
      </template>
    </el-alert>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button
        type="primary"
        :loading="submitting"
        @click="submitForm"
        :disabled="validMappingsCount === 0"
      >
        开始替换 ({{ validMappingsCount }})
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Delete, Right } from '@element-plus/icons-vue'
import { annotationApi } from '@/api'

const props = defineProps({
  datasetId: String,
  currentClasses: {
    type: Array,
    default: () => [],
  },
})

const emit = defineEmits(['success'])

const visible = ref(false)
const submitting = ref(false)
const mappings = ref([])

// COCO 80类英文到中文映射
const cocoToChinese = {
  'person': '人',
  'bicycle': '自行车',
  'car': '汽车',
  'motorcycle': '摩托车',
  'airplane': '飞机',
  'bus': '公交车',
  'train': '火车',
  'truck': '卡车',
  'boat': '船',
  'traffic light': '红绿灯',
  'fire hydrant': '消防栓',
  'stop sign': '停车标志',
  'parking meter': '停车计时器',
  'bench': '长椅',
  'bird': '鸟',
  'cat': '猫',
  'dog': '狗',
  'horse': '马',
  'sheep': '羊',
  'cow': '牛',
  'elephant': '大象',
  'bear': '熊',
  'zebra': '斑马',
  'giraffe': '长颈鹿',
  'backpack': '背包',
  'umbrella': '雨伞',
  'handbag': '手提包',
  'tie': '领带',
  'suitcase': '行李箱',
  'frisbee': '飞盘',
  'skis': '滑雪板',
  'snowboard': '滑雪板',
  'sports ball': '球',
  'kite': '风筝',
  'baseball bat': '棒球棒',
  'baseball glove': '棒球手套',
  'skateboard': '滑板',
  'surfboard': '冲浪板',
  'tennis racket': '网球拍',
  'bottle': '瓶子',
  'wine glass': '酒杯',
  'cup': '杯子',
  'fork': '叉子',
  'knife': '刀',
  'spoon': '勺子',
  'bowl': '碗',
  'banana': '香蕉',
  'apple': '苹果',
  'sandwich': '三明治',
  'orange': '橙子',
  'broccoli': '西兰花',
  'carrot': '胡萝卜',
  'hot dog': '热狗',
  'pizza': '披萨',
  'donut': '甜甜圈',
  'cake': '蛋糕',
  'chair': '椅子',
  'couch': '沙发',
  'potted plant': '盆栽',
  'bed': '床',
  'dining table': '餐桌',
  'toilet': '马桶',
  'tv': '电视',
  'laptop': '笔记本电脑',
  'mouse': '鼠标',
  'remote': '遥控器',
  'keyboard': '键盘',
  'cell phone': '手机',
  'microwave': '微波炉',
  'oven': '烤箱',
  'toaster': '烤面包机',
  'sink': '水槽',
  'refrigerator': '冰箱',
  'book': '书',
  'clock': '时钟',
  'vase': '花瓶',
  'scissors': '剪刀',
  'teddy bear': '泰迪熊',
  'hair drier': '吹风机',
  'toothbrush': '牙刷',
}

const validMappingsCount = computed(() => {
  return mappings.value.filter(m => m.oldClass && m.newClass).length
})

const open = () => {
  visible.value = true

  // 初始化一些空映射行
  if (mappings.value.length === 0) {
    addMapping()
  }
}

const addMapping = () => {
  mappings.value.push({
    oldClass: '',
    newClass: '',
  })
}

const removeMapping = (index) => {
  mappings.value.splice(index, 1)
}

const clearMappings = () => {
  mappings.value = []
  addMapping()
}

const loadPreset = (presetName) => {
  if (presetName === 'coco_to_chinese') {
    // 只添加当前数据集中存在的COCO类别
    mappings.value = []
    props.currentClasses.forEach(cls => {
      if (cocoToChinese[cls]) {
        mappings.value.push({
          oldClass: cls,
          newClass: cocoToChinese[cls],
        })
      }
    })

    if (mappings.value.length === 0) {
      ElMessage.warning('当前数据集没有COCO类别')
      addMapping()
    } else {
      ElMessage.success(`已加载 ${mappings.value.length} 个类别映射`)
    }
  } else if (presetName === 'simplify') {
    // 简化类别名（去除空格、下划线等）
    mappings.value = []
    props.currentClasses.forEach(cls => {
      const simplified = cls.replace(/[\s_-]+/g, '').toLowerCase()
      if (simplified !== cls) {
        mappings.value.push({
          oldClass: cls,
          newClass: simplified,
        })
      }
    })

    if (mappings.value.length === 0) {
      ElMessage.info('类别名称已经很简洁了')
      addMapping()
    }
  }
}

const submitForm = async () => {
  // 验证映射
  const validMappings = mappings.value.filter(m => m.oldClass && m.newClass)

  if (validMappings.length === 0) {
    ElMessage.warning('请至少添加一个类别映射')
    return
  }

  // 检查是否有重复的原类别
  const oldClasses = validMappings.map(m => m.oldClass)
  const uniqueOldClasses = new Set(oldClasses)
  if (oldClasses.length !== uniqueOldClasses.size) {
    ElMessage.warning('原类别中有重复项，请检查')
    return
  }

  // 构建映射对象
  const classMapping = {}
  validMappings.forEach(m => {
    classMapping[m.oldClass] = m.newClass
  })

  // 确认操作
  try {
    await ElMessageBox.confirm(
      `确定要替换 ${validMappings.length} 个类别吗？此操作不可撤销！`,
      '确认替换',
      {
        confirmButtonText: '确定替换',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )
  } catch {
    return // 用户取消
  }

  submitting.value = true
  try {
    const result = await annotationApi.batchReplaceClasses({
      dataset_id: props.datasetId,
      class_mapping: classMapping,
    })

    ElMessage.success(result.message || `成功替换 ${result.updated_count} 个标注`)
    visible.value = false
    emit('success', result)
  } catch (error) {
    console.error('Batch replace failed:', error)
    ElMessage.error(error.response?.data?.detail || '批量替换失败')
  } finally {
    submitting.value = false
  }
}

const onClose = () => {
  // 可选：清空映射
}

defineExpose({
  open,
})
</script>

<style scoped>
:deep(.el-table) {
  font-size: 13px;
}

:deep(.el-select) {
  width: 100%;
}
</style>

