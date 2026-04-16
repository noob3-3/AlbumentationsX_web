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
                  :label="datasetOptionLabel(d)"
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
              <el-select v-model="form.model_name" style="width:100%" :loading="baseCheckpointLoading">
                <el-option-group label="YOLO11">
                  <el-option v-for="m in yolo11BaseModels" :key="m" :label="m" :value="m"/>
                </el-option-group>
                <el-option-group label="YOLOv8">
                  <el-option v-for="m in yolov8BaseModels" :key="m" :label="m" :value="m"/>
                </el-option-group>
              </el-select>
              <div v-if="modelTaskHint" class="model-task-hint">{{ modelTaskHint }}</div>
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
                placeholder="选择要继续训练的模型（已自动选中最优）"
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
                v-if="availableModels.length === 0"
                style="margin-top: 8px"
                type="warning"
                :closable="false"
              >
                <template #title>当前项目尚无已训练模型，请先完成一次训练</template>
              </el-alert>
              <el-alert
                v-else
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
              <el-input-number v-model="form.epochs" :min="1" :max="10000" />
            </el-form-item>
            <el-form-item label="批大小">
              <el-input-number v-model="form.batch_size" :min="batchSizeMin" :max="512" />
              <div v-if="form.device === '0,1'" style="color: #909399; font-size: 12px; margin-top: 4px">
                双卡时 batch 平分到每卡，需 ≥ 2
              </div>
            </el-form-item>
            <el-form-item label="图片尺寸">
              <div style="display: flex; align-items: center; gap: 8px">
                <el-input-number v-model="form.img_size" :min="32" :max="8192" :step="32" controls-position="right" style="width: 130px" />
                <span>×</span>
                <el-input-number v-model="form.img_size_2" :min="32" :max="8192" :step="32" controls-position="right" style="width: 130px" />
              </div>
              <div style="color: #909399; font-size: 12px; margin-top: 4px">对应imgsz参数，建议为32的倍数</div>
            </el-form-item>
            <el-form-item label="初始学习率">
              <el-input-number v-model="form.learning_rate" :min="0.0000001" :max="0.1" :step="0.00001" :precision="7" controls-position="right" style="width: 200px" />
              <span style="color: #909399; font-size: 12px; margin-left: 8px">lr0</span>
            </el-form-item>
            <el-form-item label="验证集">
              <div style="display: flex; flex-direction: column; gap: 8px;">
                <div style="display: flex; align-items: center; gap: 8px;">
                  <el-checkbox v-model="form.use_validation_dataset">
                    使用独立验证集（从下方选择数据集）
                  </el-checkbox>
                </div>
                <template v-if="form.use_validation_dataset">
                  <el-form-item prop="validation_dataset_id" style="margin-bottom: 0">
                  <el-select
                    v-model="form.validation_dataset_id"
                    placeholder="选择验证集数据集"
                    style="width: 100%"
                    filterable
                  >
                    <el-option
                      v-for="d in validationDatasetOptions"
                      :key="d.id"
                      :label="formatValidationDatasetOption(d)"
                      :value="d.id"
                    />
                  </el-select>
                  </el-form-item>
                  <!-- 选中验证集的标注情况 -->
                  <el-alert
                    v-if="selectedValidationDatasetInfo"
                    :type="selectedValidationDatasetInfo.annotated_image_count > 0 ? 'success' : 'warning'"
                    :closable="false"
                    show-icon
                  >
                    <template #title>
                      <div style="font-size: 12px">
                        验证集: {{ selectedValidationDatasetInfo.annotated_image_count }} 张已标注 / {{ selectedValidationDatasetInfo.total_images }} 张总计
                        <span v-if="selectedValidationDatasetInfo.augmented_count > 0">
                          （原始 {{ selectedValidationDatasetInfo.original_annotated_count }}/{{ selectedValidationDatasetInfo.original_count }}，增强 {{ selectedValidationDatasetInfo.augmented_annotated_count }}/{{ selectedValidationDatasetInfo.augmented_count }}）
                        </span>
                      </div>
                    </template>
                  </el-alert>
                </template>
                <div v-else>
                  <el-slider v-model="form.val_split" :min="0.1" :max="0.4" :step="0.05" :format-tooltip="(v) => `${(v*100).toFixed(0)}%`" style="width:200px" />
                  <span style="margin-left:12px">{{ (form.val_split * 100).toFixed(0) }}% 从训练集划分</span>
                </div>
              </div>
            </el-form-item>
            <el-form-item label="设备">
              <el-radio-group v-model="form.device">
                <el-radio value="auto">自动</el-radio>
                <el-radio value="cpu">CPU</el-radio>
                <el-radio value="0">GPU 0</el-radio>
                <el-radio value="1">GPU 1</el-radio>
                <el-radio value="0,1">GPU 0+1 (双卡)</el-radio>
              </el-radio-group>
              <div v-if="form.device === '0,1'" style="color: #909399; font-size: 12px; margin-top: 4px">
                双卡并行，适合 4096 等大尺寸训练；batch_size 需 ≥ 2
              </div>
            </el-form-item>
            <el-divider />

            <!-- 早停和保存策略 -->
            <el-form-item label="早停耐心值">
              <el-input-number v-model="form.patience" :min="0" :max="1000" style="width: 150px" />
              <el-text size="small" type="info" style="margin-left: 12px">连续N轮验证指标无改善则停止，0=禁用早停（训练满全部轮数）</el-text>
            </el-form-item>
            <el-form-item label="保存策略">
              <el-input-number v-model="form.save_period" :min="-1" :max="1000" style="width: 150px" />
              <el-text size="small" type="info" style="margin-left: 12px">每N轮保存，-1=仅保存最佳和最后</el-text>
            </el-form-item>

            <!-- 高级训练参数折叠面板 -->
            <el-collapse v-model="activeCollapse" style="margin-top: 12px; margin-bottom: 16px; border: none">

              <!-- 学习率与正则化 -->
              <el-collapse-item title="学习率与正则化" name="lr">
                <el-form-item label="最终LR因子">
                  <el-input-number v-model="form.lrf" :min="0.0000001" :max="1.0" :step="0.0001" :precision="7" controls-position="right" style="width: 200px" />
                  <div style="color: #909399; font-size: 12px; margin-top: 2px">最终LR = lr0 × lrf = {{ (form.learning_rate * form.lrf).toExponential(2) }}</div>
                </el-form-item>
                <el-form-item label="预热轮数">
                  <el-input-number v-model="form.warmup_epochs" :min="0" :max="100" :step="1" style="width: 150px" />
                  <el-text size="small" type="info" style="margin-left: 8px">warmup_epochs</el-text>
                </el-form-item>
                <el-form-item label="权重衰减">
                  <el-input-number v-model="form.weight_decay" :min="0" :max="0.1" :step="0.001" :precision="4" controls-position="right" style="width: 200px" />
                  <el-text size="small" type="info" style="margin-left: 8px">L2正则化</el-text>
                </el-form-item>
                <el-form-item label="Dropout">
                  <el-slider v-model="form.dropout" :min="0" :max="1" :step="0.05" style="width: 200px" />
                  <span style="margin-left: 12px; min-width: 36px; display: inline-block">{{ form.dropout.toFixed(2) }}</span>
                </el-form-item>
              </el-collapse-item>

              <!-- 数据增强参数 -->
              <el-collapse-item title="数据增强参数" name="augmentation">
                <el-form-item label="启用增强">
                  <el-switch v-model="form.augment" />
                </el-form-item>
                <template v-if="form.augment">
                  <el-form-item label="HSV色调(H)">
                    <el-slider v-model="form.hsv_h" :min="0" :max="1" :step="0.01" style="width: 200px" />
                    <span style="margin-left: 12px; min-width: 36px; display: inline-block">{{ form.hsv_h.toFixed(2) }}</span>
                  </el-form-item>
                  <el-form-item label="HSV饱和度(S)">
                    <el-slider v-model="form.hsv_s" :min="0" :max="1" :step="0.01" style="width: 200px" />
                    <span style="margin-left: 12px; min-width: 36px; display: inline-block">{{ form.hsv_s.toFixed(2) }}</span>
                  </el-form-item>
                  <el-form-item label="HSV亮度(V)">
                    <el-slider v-model="form.hsv_v" :min="0" :max="1" :step="0.01" style="width: 200px" />
                    <span style="margin-left: 12px; min-width: 36px; display: inline-block">{{ form.hsv_v.toFixed(2) }}</span>
                  </el-form-item>
                  <el-form-item label="旋转角度">
                    <el-input-number v-model="form.degrees" :min="0" :max="180" :step="1" :precision="1" style="width: 150px" />
                    <el-text size="small" type="info" style="margin-left: 8px">±度</el-text>
                  </el-form-item>
                  <el-form-item label="平移">
                    <el-slider v-model="form.translate" :min="0" :max="1" :step="0.01" style="width: 200px" />
                    <span style="margin-left: 12px; min-width: 36px; display: inline-block">{{ form.translate.toFixed(2) }}</span>
                  </el-form-item>
                  <el-form-item label="缩放">
                    <el-slider v-model="form.scale" :min="0" :max="1" :step="0.01" style="width: 200px" />
                    <span style="margin-left: 12px; min-width: 36px; display: inline-block">{{ form.scale.toFixed(2) }}</span>
                  </el-form-item>
                  <el-form-item label="剪切">
                    <el-input-number v-model="form.shear" :min="0" :max="90" :step="0.1" :precision="1" style="width: 150px" />
                    <el-text size="small" type="info" style="margin-left: 8px">±度</el-text>
                  </el-form-item>
                  <el-form-item label="透视变换">
                    <el-input-number v-model="form.perspective" :min="0" :max="0.01" :step="0.0001" :precision="4" controls-position="right" style="width: 200px" />
                  </el-form-item>
                  <el-form-item label="上下翻转">
                    <el-slider v-model="form.flipud" :min="0" :max="1" :step="0.05" style="width: 200px" />
                    <span style="margin-left: 12px; min-width: 36px; display: inline-block">{{ form.flipud.toFixed(2) }}</span>
                  </el-form-item>
                  <el-form-item label="左右翻转">
                    <el-slider v-model="form.fliplr" :min="0" :max="1" :step="0.05" style="width: 200px" />
                    <span style="margin-left: 12px; min-width: 36px; display: inline-block">{{ form.fliplr.toFixed(2) }}</span>
                  </el-form-item>
                  <el-form-item label="Mosaic">
                    <el-slider v-model="form.mosaic" :min="0" :max="1" :step="0.05" style="width: 200px" />
                    <span style="margin-left: 12px; min-width: 36px; display: inline-block">{{ form.mosaic.toFixed(2) }}</span>
                  </el-form-item>
                  <el-form-item label="MixUp">
                    <el-slider v-model="form.mixup" :min="0" :max="1" :step="0.05" style="width: 200px" />
                    <span style="margin-left: 12px; min-width: 36px; display: inline-block">{{ form.mixup.toFixed(2) }}</span>
                  </el-form-item>
                </template>
              </el-collapse-item>

              <!-- 损失函数权重 -->
              <el-collapse-item title="损失函数权重" name="loss">
                <el-form-item label="边界框(box)">
                  <el-input-number v-model="form.box" :min="0" :max="20" :step="0.1" :precision="2" style="width: 150px" />
                  <el-text size="small" type="info" style="margin-left: 8px">边界框回归损失权重</el-text>
                </el-form-item>
                <el-form-item label="分类(cls)">
                  <el-input-number v-model="form.cls" :min="0" :max="20" :step="0.1" :precision="2" style="width: 150px" />
                  <el-text size="small" type="info" style="margin-left: 8px">分类损失权重</el-text>
                </el-form-item>
                <el-form-item label="DFL(dfl)">
                  <el-input-number v-model="form.dfl" :min="0" :max="20" :step="0.1" :precision="2" style="width: 150px" />
                  <el-text size="small" type="info" style="margin-left: 8px">分布焦点损失权重</el-text>
                </el-form-item>
              </el-collapse-item>

              <!-- 高级参数 -->
              <el-collapse-item title="高级参数" name="advanced">
                <el-form-item label="关闭Mosaic">
                  <el-input-number v-model="form.close_mosaic" :min="0" :max="100" style="width: 150px" />
                  <el-text size="small" type="info" style="margin-left: 8px">最后N轮关闭Mosaic</el-text>
                </el-form-item>
                <el-form-item label="名义批大小">
                  <el-input-number v-model="form.nbs" :min="1" :max="256" style="width: 150px" />
                  <el-text size="small" type="info" style="margin-left: 8px">nbs，用于梯度累积</el-text>
                </el-form-item>
                <el-form-item label="重叠掩码">
                  <el-switch v-model="form.overlap_mask" />
                  <el-text size="small" type="info" style="margin-left: 8px">分割任务时允许掩码重叠</el-text>
                </el-form-item>
                <el-form-item label="单类别模式">
                  <el-switch v-model="form.single_cls" />
                  <el-text size="small" type="info" style="margin-left: 8px">将所有类别视为一类</el-text>
                </el-form-item>
                <el-form-item label="保存结果">
                  <el-switch v-model="form.save" />
                </el-form-item>
                <el-form-item label="训练时验证">
                  <el-switch v-model="form.val" />
                </el-form-item>
              </el-collapse-item>
            </el-collapse>

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
                <el-tooltip
                    :content="jobTrainingWeightsTooltip(job)"
                    placement="top"
                    :disabled="!jobTrainingWeightsTooltip(job)"
                >
                  <span class="job-model">{{ jobTrainingWeightsLabel(job) }}</span>
                </el-tooltip>
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
                      v-if="job.status === 'running'"
                      link
                      type="primary"
                      size="small"
                      @click.stop="downloadJobBestSnapshot(job.id, job.name)"
                      title="下载当前验证集最佳权重快照（best.pt）"
                  >下载最佳
                  </el-button>
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
import {computed, onMounted, onUnmounted, ref, watch} from 'vue'
import {Refresh} from '@element-plus/icons-vue'
import {ElMessage} from 'element-plus'
import {downloadTrainingJobBestFile, trainingApi} from '@/api'
import {useTrainingStore} from '@/stores/training'
import {useDatasetStore} from '@/stores/dataset'
import {useProjectStore} from '@/stores/project'
import {storeToRefs} from 'pinia'
import {useRouter} from 'vue-router'

const router = useRouter()

function jobTrainingWeightsLabel(job) {
  return job?.extra_params?.effective_model_label || job?.model_name || '—'
}

function jobTrainingWeightsTooltip(job) {
  const p = job?.extra_params?.effective_model_path
  if (!p || String(p).trim() === '') return ''
  const label = jobTrainingWeightsLabel(job)
  return String(p).trim() === label ? '' : String(p).trim()
}

async function downloadJobBestSnapshot(jobId, jobName) {
  try {
    await downloadTrainingJobBestFile(jobId, jobName || 'training')
    ElMessage.success('已开始下载')
  } catch (e) {
    ElMessage.error(e?.message || '下载失败')
  }
}

const trainingStore = useTrainingStore()
const datasetStore = useDatasetStore()
const projectStore = useProjectStore()
const { jobs } = storeToRefs(trainingStore)
const { datasets } = storeToRefs(datasetStore)
const { hasProject, projectId } = storeToRefs(projectStore)

const formRef = ref()
const creating = ref(false)
/** 注册表中可选的「继续训练」模型 */
const availableModels = ref([])
/** 基础权重列表（与后端 GET /training/available-models 一致，含 obb/pose） */
const baseCheckpointModels = ref([])
const baseCheckpointLoading = ref(false)
const datasetClasses = ref([])
const selectedDatasetInfo = ref(null)
const selectedValidationDatasetInfo = ref(null)
const validationDatasetStatsCache = ref({})  // { datasetId: stats }

const activeCollapse = ref([])

const form = ref({
  name: '选择数据集和模型后自动生成',
  dataset_id: '',
  model_name: 'yolov8n.pt',
  epochs: 400,
  batch_size: 4,
  img_size: 640,
  img_size_2: 640,
  learning_rate: 0.00001,
  val_split: 0.2,
  device: '0',

  // 验证集：使用独立数据集或按比例划分
  use_validation_dataset: false,
  validation_dataset_id: '',

  // 使用增强数据
  use_augmented_data: true,

  // 继续训练
  resume_training: false,
  base_model_id: '',

  // 类别增强
  use_class_enhancement: false,
  focus_classes: [],

  // 训练控制
  save: true,
  val: true,
  patience: 100,
  save_period: -1,

  // 数据增强
  augment: true,
  hsv_h: 0.1,
  hsv_s: 0.9,
  hsv_v: 0.5,
  degrees: 15.0,
  translate: 0.2,
  scale: 0.3,
  shear: 0.2,
  perspective: 0.001,
  flipud: 0.5,
  fliplr: 0.5,
  mosaic: 1.0,
  mixup: 0.2,

  // 正则化
  dropout: 0.5,
  weight_decay: 0.01,

  // 学习率策略
  lrf: 0.0001,
  warmup_epochs: 40,

  // 损失函数权重
  box: 0.1,
  cls: 0.3,
  dfl: 1.5,

  // 高级参数
  close_mosaic: 5,
  overlap_mask: true,
  single_cls: false,
  nbs: 16,
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
  validation_dataset_id: [{
    required: false,
    validator: (rule, value, callback) => {
      if (form.value.use_validation_dataset && !value) {
        callback(new Error('请选择验证集数据集'))
      } else {
        callback()
      }
    }
  }],
}

const selectedDatasetLabelTask = computed(() => {
  const d = datasets.value.find((x) => x.id === form.value.dataset_id)
  return d?.label_task || 'detect'
})

function filterCheckpointModelsByLabelTask(list, task, hasDataset) {
  if (!hasDataset) return list
  const t = task || 'detect'
  return list.filter((m) => {
    const low = (m || '').toLowerCase()
    const isObb = low.includes('-obb')
    const isPose = low.includes('-pose')
    if (t === 'obb') return isObb
    if (t === 'pose') return isPose
    return !isObb && !isPose
  })
}

// yolo11*、yolov11*（含 obb/pose）归为 YOLO11 组；yolov8* 归为 YOLOv8 组；按数据集 label_task 过滤
const yolo11BaseModels = computed(() => {
  const raw = baseCheckpointModels.value.filter((m) => /^yolo11|^yolov11/.test(m))
  return filterCheckpointModelsByLabelTask(raw, selectedDatasetLabelTask.value, !!form.value.dataset_id)
})
const yolov8BaseModels = computed(() => {
  const raw = baseCheckpointModels.value.filter((m) => /^yolov8/.test(m))
  return filterCheckpointModelsByLabelTask(raw, selectedDatasetLabelTask.value, !!form.value.dataset_id)
})

/** 与后端 infer_ultralytics_task_from_model_name 一致，用于界面提示 */
function inferModelTaskFromFilename(name) {
  const m = (name || '').toLowerCase()
  if (m.includes('-pose')) return 'pose'
  if (m.includes('-obb')) return 'obb'
  if (m.includes('-seg')) return 'segment'
  return 'detect'
}

const modelTaskHint = computed(() => {
  const t = inferModelTaskFromFilename(form.value.model_name)
  const hints = {
    detect: '检测模型：与本平台「水平框」标注一致。',
    pose: '姿态模型：训练时会导出为带关键点的 pose 格式（由框/多边形生成，不等同于专业骨架标注）。',
    obb: 'OBB 模型：水平框会导出为轴对齐四顶点；四点多边形按顶点顺序导出。',
    segment: '分割模型需要掩码标注，本平台无法生成，创建训练任务时将被拒绝；请换用检测或 OBB。',
  }
  return hints[t] || ''
})

let refreshTimer = null

function datasetOptionLabel(d) {
  const tag = d.label_task && d.label_task !== 'detect' ? ` · ${d.label_task}` : ''
  return `${d.name} (${d.image_count}张)${tag}`
}

const statusType = (s) => ({ pending: 'info', running: 'warning', completed: 'success', failed: 'danger', cancelled: '' })[s] || ''
const statusText = (s) => ({ pending: '等待', running: '训练中', completed: '完成', failed: '失败', cancelled: '已取消' })[s] || s
const formatDate = (d) => d ? new Date(d).toLocaleString('zh-CN', { hour12: false }) : '-'

onMounted(async () => {
  await Promise.all([
    fetchJobs(),
    datasetStore.fetchDatasets(),
    fetchAvailableModels(),
    fetchBaseCheckpointModels(),
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

// 双卡时 batch 平分到每卡，最小需为 2
const batchSizeMin = computed(() => (form.value.device === '0,1' ? 2 : 1))

// 验证集可选数据集（排除当前训练集）
const validationDatasetOptions = computed(() => {
  const trainId = form.value.dataset_id
  return datasets.value.filter(d => d.id !== trainId)
})

function formatValidationDatasetOption(d) {
  const stats = validationDatasetStatsCache.value[d.id]
  if (stats) {
    return `${d.name} (${d.image_count}张，已标注 ${stats.annotated_image_count}/${stats.total_images} 张)`
  }
  return `${d.name} (${d.image_count}张)`
}

// 监听数据集变化，加载类别列表
watch(() => form.value.dataset_id, () => {
  loadDatasetClasses()
  updateJobName()
  loadDatasetInfo()
  if (form.value.validation_dataset_id === form.value.dataset_id) {
    form.value.validation_dataset_id = ''
  }
  selectedValidationDatasetInfo.value = null
  validationDatasetStatsCache.value = {}
})

// 监听使用独立验证集或验证集ID变化，加载选中验证集的标注统计
watch(() => [form.value.use_validation_dataset, form.value.validation_dataset_id], ([useVal, valId]) => {
  if (!useVal || !valId) {
    selectedValidationDatasetInfo.value = null
    return
  }
  loadValidationDatasetInfo()
})

// 监听设备：切到双卡时若 batch_size<2 自动修正
watch(() => form.value.device, (device) => {
  if (device === '0,1' && form.value.batch_size < 2) form.value.batch_size = 2
})

// 监听模型名称变化，更新任务名称
watch(() => form.value.model_name, () => {
  updateJobName()
})

// 选择数据集后，基础模型列表会随 label_task 变化；当前模型若不在列表中则切换到第一个可用权重
watch(
    [yolo11BaseModels, yolov8BaseModels, () => form.value.dataset_id],
    () => {
      const merged = [...yolo11BaseModels.value, ...yolov8BaseModels.value]
      if (!form.value.dataset_id || !merged.length) return
      if (!merged.includes(form.value.model_name)) {
        form.value.model_name = merged[0]
      }
    },
)

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
  const params = {}
  if (projectId.value) {
    params.project_id = projectId.value
  }
  await trainingStore.fetchJobs(params)
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

/** 训练页「基础模型」下拉：与后端 AVAILABLE_MODELS 同步 */
async function fetchBaseCheckpointModels() {
  baseCheckpointLoading.value = true
  try {
    const res = await trainingApi.availableModels()
    const list = res.models || []
    baseCheckpointModels.value = Array.isArray(list) ? list : []
  } catch (error) {
    console.error('Failed to fetch base checkpoint models:', error)
    baseCheckpointModels.value = [
      'yolo11n.pt', 'yolo11s.pt', 'yolo11m.pt', 'yolo11l.pt', 'yolo11x.pt',
      'yolo11n-obb.pt', 'yolo11n-pose.pt',
      'yolov8n.pt', 'yolov8s.pt', 'yolov8m.pt', 'yolov8l.pt', 'yolov8x.pt',
      'yolov8n-obb.pt', 'yolov8n-pose.pt',
      'yolo11n-det.pt', 'yolo11s-det.pt',
    ]
  } finally {
    baseCheckpointLoading.value = false
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

async function loadValidationDatasetInfo() {
  const valId = form.value.validation_dataset_id
  if (!valId || !form.value.use_validation_dataset) {
    selectedValidationDatasetInfo.value = null
    return
  }

  try {
    const { datasetApi } = await import('@/api')
    const stats = await datasetApi.getStats(valId)
    validationDatasetStatsCache.value[valId] = stats
    selectedValidationDatasetInfo.value = {
      total_images: stats.total_images,
      original_count: stats.original_count,
      augmented_count: stats.augmented_count,
      annotated_image_count: stats.annotated_image_count,
      original_annotated_count: stats.original_annotated_count,
      augmented_annotated_count: stats.augmented_annotated_count,
    }
  } catch (error) {
    console.error('Failed to load validation dataset info:', error)
    selectedValidationDatasetInfo.value = null
  }
}

function goToAnnotation() {
  const query = {}
  if (form.value.dataset_id) {
    query.dataset = form.value.dataset_id
  }
  const m = (form.value.model_name || '').toLowerCase()
  if (m.includes('-obb')) query.mode = 'obb'
  else if (m.includes('-pose')) query.mode = 'pose'
  router.push(Object.keys(query).length ? {path: '/annotation', query} : '/annotation')
}

async function onResumeTrainingChange(value) {
  if (value) {
    // 启用继续训练时，建议减少训练轮数
    if (form.value.epochs > 50) {
      ElMessage.info('继续训练建议减少训练轮数（已自动调整为50轮）')
      form.value.epochs = 50
    }
    // 加载可用模型列表
    await fetchAvailableModels()
    // 自动选择模型：仅1个时直接选中；多个时选 mAP50 最高的
    const models = availableModels.value
    if (models.length === 1) {
      form.value.base_model_id = models[0].id
    } else if (models.length > 1) {
      const best = models.reduce((a, b) => ((a?.map50 ?? 0) >= (b?.map50 ?? 0) ? a : b))
      form.value.base_model_id = best.id
    }
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
    const payload = { ...form.value }
    if (!payload.use_validation_dataset) {
      delete payload.validation_dataset_id
    }
    // 继续训练时必须包含 base_model_id，避免后端误用默认模型
    if (payload.resume_training) {
      if (!payload.base_model_id) {
        ElMessage.warning('请选择要继续训练的基础模型')
        creating.value = false
        return
      }
    } else {
      delete payload.base_model_id
    }
    const job = await trainingStore.createJob(payload)
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
.model-task-hint {
  margin-top: 8px;
  font-size: 12px;
  color: #606266;
  line-height: 1.5;
}
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
