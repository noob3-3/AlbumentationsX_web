<template>
  <div>
    <div class="page-header">
      <h2>数据集管理</h2>
      <p>管理所有训练数据集</p>
    </div>

    <!-- Project Warning -->
    <el-alert
      v-if="!hasProject"
      type="warning"
      title="请先在页面顶部选择一个项目"
      description="选择项目后，将只显示该项目的数据集"
      :closable="false"
      style="margin-bottom: 16px"
      show-icon
    />

    <el-card shadow="never">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <span>数据集列表</span>
          <el-button type="primary" :icon="Plus" @click="showCreate = true">新建数据集</el-button>
        </div>
      </template>

      <el-table :data="datasets" v-loading="loading" stripe>
        <el-table-column prop="name" label="名称" min-width="160">
          <template #default="{ row }">
            <el-link type="primary" @click="$router.push(`/datasets/${row.id}`)">{{ row.name }}</el-link>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="描述" min-width="200" show-overflow-tooltip />
        <el-table-column prop="image_count" label="图片数" width="100" align="center" />
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
            <el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="160">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="$router.push(`/datasets/${row.id}`)">查看</el-button>
            <el-button link type="primary" size="small" @click="$router.push(`/collect?dataset=${row.id}`)">采集</el-button>
            <el-popconfirm title="确认删除该数据集?" @confirm="handleDelete(row.id)">
              <template #reference>
                <el-button link type="danger" size="small">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Create Dialog -->
    <el-dialog v-model="showCreate" title="新建数据集" width="480px">
      <el-form :model="form" label-width="80px" :rules="rules" ref="formRef">
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" placeholder="输入数据集名称" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="3" placeholder="可选描述" />
        </el-form-item>
        <el-form-item label="类别">
          <el-select
            v-model="form.classes"
            multiple
            filterable
            allow-create
            placeholder="输入类别名称后回车"
            style="width: 100%"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="handleCreate">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { useDatasetStore } from '@/stores/dataset'
import { useProjectStore } from '@/stores/project'
import { storeToRefs } from 'pinia'

const store = useDatasetStore()
const projectStore = useProjectStore()
const { datasets, loading } = storeToRefs(store)
const { hasProject, projectId } = storeToRefs(projectStore)

const showCreate = ref(false)
const creating = ref(false)
const formRef = ref()
const form = ref({ name: '', description: '', classes: [] })
const rules = { name: [{ required: true, message: '请输入名称' }] }

const statusType = (s) => ({ active: 'success', pending: 'info', ready: 'success', error: 'danger' })[s] || ''
const formatDate = (d) => d ? new Date(d).toLocaleString('zh-CN', { hour12: false }) : '-'

onMounted(() => store.fetchDatasets())

watch(projectId, () => store.fetchDatasets())

async function handleCreate() {
  await formRef.value.validate()
  creating.value = true
  try {
    await store.createDataset(form.value)
    showCreate.value = false
    form.value = { name: '', description: '', classes: [] }
  } finally {
    creating.value = false
  }
}

async function handleDelete(id) {
  await store.deleteDataset(id)
}
</script>
