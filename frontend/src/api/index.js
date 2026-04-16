import http from '@/utils/http'

// Project APIs
export const projectApi = {
  list: (params) => http.get('/projects', { params }),
  create: (data) => http.post('/projects', data),
  get: (id) => http.get(`/projects/${id}`),
  update: (id, data) => http.put(`/projects/${id}`, data),
  delete: (id) => http.delete(`/projects/${id}`),
  getDatasets: (id, params) => http.get(`/projects/${id}/datasets`, { params }),
  getModels: (id, params) => http.get(`/projects/${id}/models`, { params }),
  updateCounts: (id) => http.post(`/projects/${id}/update-counts`),
  testWebhook: (id) => http.post(`/projects/${id}/test-webhook`),
}

// Dataset APIs
export const datasetApi = {
  list: (params) => http.get('/datasets', { params }),
  create: (data) => http.post('/datasets', data),
  get: (id) => http.get(`/datasets/${id}`),
  update: (id, data) => http.put(`/datasets/${id}`, data),
  delete: (id) => http.delete(`/datasets/${id}`),

  // Images
  uploadImages: (datasetId, formData, onProgress) =>
    http.post(`/datasets/${datasetId}/images/upload`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: onProgress,
      timeout: 600000, // 10 minutes for large batch uploads
    }),
    uploadImagesWithLabels: (datasetId, formData, onProgress, labelFormat = 'auto') =>
        http.post(
            `/datasets/${datasetId}/images/upload-with-labels?label_format=${encodeURIComponent(labelFormat)}`,
            formData,
            {
                headers: {'Content-Type': 'multipart/form-data'},
                onUploadProgress: onProgress,
                timeout: 600000, // 10 minutes for large batch uploads
            },
        ),
  collectFromUrls: (datasetId, data) =>
    http.post(`/datasets/${datasetId}/images/collect-from-urls`, data),
  listImages: (datasetId, params) =>
    http.get(`/datasets/${datasetId}/images`, { params }),
  getImage: (datasetId, imageId) =>
    http.get(`/datasets/${datasetId}/images/${imageId}`),
  deleteImage: (datasetId, imageId) =>
    http.delete(`/datasets/${datasetId}/images/${imageId}`),
  moveImage: (datasetId, imageId, targetDatasetId) =>
    http.post(`/datasets/${datasetId}/images/${imageId}/move`, null, { params: { target_dataset_id: targetDatasetId } }),

  // 数据集统计
  getStats: (datasetId) => http.get(`/datasets/${datasetId}/stats`),

  // 导出数据集（YOLO 格式 ZIP），返回 blob 用于触发下载
  export: (datasetId, params = {}) => http.get(`/datasets/${datasetId}/export`, { params, responseType: 'blob' }),

  // 删除类别及其标注
  deleteClass: (datasetId, className) =>
    http.delete(`/datasets/${datasetId}/classes/${encodeURIComponent(className)}`),

  // Serve
  imageUrl: (imageId, thumbnail = false) =>
    `/api/v1/datasets/files/image/${imageId}${thumbnail ? '?thumbnail=true' : ''}`,
}

// Augmentation APIs
export const augmentationApi = {
  createJob: (data) => http.post('/augmentation/jobs', data),
  listJobs: (params) => http.get('/augmentation/jobs', { params }),
  getJob: (id) => http.get(`/augmentation/jobs/${id}`),
  listTransforms: () => http.get('/augmentation/transforms'),
  getDefaultConfig: () => http.get('/augmentation/default-config'),
  getRecommendedConfigs: () => http.get('/augmentation/recommended-configs'),
}

// Training APIs
export const trainingApi = {
  createJob: (data) => http.post('/training/jobs', data),
  listJobs: (params) => http.get('/training/jobs', { params }),
  getJob: (id) => http.get(`/training/jobs/${id}`),
  cancelJob: (id) => http.post(`/training/jobs/${id}/cancel`),
  stopJob: (id) => http.post(`/training/jobs/${id}/stop`),
    downloadJobBestUrl: (jobId) => `/api/v1/training/jobs/${jobId}/download-best`,
  availableModels: () => http.get('/training/available-models'),

  // Models
  listModels: (params) => http.get('/training/models', { params }),
  getModel: (id) => http.get(`/training/models/${id}`),
  importModel: (formData) => http.post('/training/models/import', formData),
  deleteModel: (id) => http.delete(`/training/models/${id}`),
  downloadModel: (id) => `/api/v1/training/models/${id}/download`,
  downloadModelPackage: (id) => `/api/v1/training/models/${id}/download-package`,
}

/**
 * 下载训练 run 目录下当前的 best.pt（训练中即可拉取快照）。失败抛出 Error(message 为服务端 detail)。
 */
export async function downloadTrainingJobBestFile(jobId, nameHint = 'training') {
    const res = await fetch(`${window.location.origin}/api/v1/training/jobs/${jobId}/download-best`, {
        credentials: 'include',
    })
    if (!res.ok) {
        let detail = '下载失败'
        try {
            const j = await res.json()
            if (typeof j.detail === 'string') detail = j.detail
            else if (Array.isArray(j.detail) && j.detail[0]?.msg) detail = j.detail[0].msg
        } catch {
            /* ignore */
        }
        throw new Error(detail)
    }
    const blob = await res.blob()
    const cd = res.headers.get('content-disposition')
    let filename = `${nameHint}_training_best.pt`
    if (cd) {
        const utf8 = /filename\*=UTF-8''([^;\s]+)/i.exec(cd)
        if (utf8) {
            try {
                filename = decodeURIComponent(utf8[1])
            } catch {
                filename = utf8[1]
            }
        } else {
            const m = /filename="([^"]+)"/i.exec(cd) || /filename=([^;\s]+)/i.exec(cd)
            if (m) filename = m[1].replace(/["']/g, '')
        }
    }
    const url = URL.createObjectURL(blob)
    try {
        const a = document.createElement('a')
        a.href = url
        a.download = filename
        a.click()
    } finally {
        URL.revokeObjectURL(url)
    }
}

/** @param {Record<string, unknown>} [opts] */
function appendOnnxQuery(q, opts = {}) {
    q.set('opset', String(opts.opset ?? 18))
    q.set('dynamic', String(!!opts.dynamic))
    q.set('batch', String(opts.batch ?? 1))
    q.set('simplify', String(!!opts.simplify))
    q.set('half', String(!!opts.half))
    if (opts.imgsz != null && opts.imgsz !== '') {
        q.set('imgsz', String(opts.imgsz))
    }
}

export function buildTrainingModelOnnxUrl(modelId, opts = {}) {
    const q = new URLSearchParams()
    appendOnnxQuery(q, opts)
    return `/api/v1/training/models/${modelId}/export-onnx?${q.toString()}`
}

export function buildTrainingJobOnnxUrl(jobId, opts = {}) {
    const q = new URLSearchParams()
    appendOnnxQuery(q, opts)
    return `/api/v1/training/jobs/${jobId}/export-onnx?${q.toString()}`
}

/** @param {string} pathWithQuery 以 /api/v1 开头的路径（含 query） */
export async function downloadOnnxExport(pathWithQuery) {
    const res = await fetch(`${window.location.origin}${pathWithQuery}`, {
        credentials: 'include',
    })
    if (!res.ok) {
        let detail = 'ONNX 导出失败'
        try {
            const j = await res.json()
            if (typeof j.detail === 'string') detail = j.detail
            else if (Array.isArray(j.detail) && j.detail[0]?.msg) detail = j.detail[0].msg
        } catch {
            /* ignore */
        }
        throw new Error(detail)
    }
    const blob = await res.blob()
    const cd = res.headers.get('content-disposition')
    let filename = 'model.onnx'
    if (cd) {
        const utf8 = /filename\*=UTF-8''([^;\s]+)/i.exec(cd)
        if (utf8) {
            try {
                filename = decodeURIComponent(utf8[1])
            } catch {
                filename = utf8[1]
            }
        } else {
            const m = /filename="([^"]+)"/i.exec(cd) || /filename=([^;\s]+)/i.exec(cd)
            if (m) filename = m[1].replace(/["']/g, '')
        }
    }
    const url = URL.createObjectURL(blob)
    try {
        const a = document.createElement('a')
        a.href = url
        a.download = filename
        a.click()
    } finally {
        URL.revokeObjectURL(url)
    }
}

// Annotation APIs
export const annotationApi = {
  updateImageAnnotations: (imageId, data) =>
    http.put(`/annotation/images/${imageId}`, data),
  getImageAnnotations: (imageId) =>
    http.get(`/annotation/images/${imageId}`),
  deleteImageAnnotations: (imageId) =>
    http.delete(`/annotation/images/${imageId}`),
  autoAnnotate: (data) =>
    http.post('/annotation/auto-annotate', data),
  listPretrainedModels: () =>
    http.get('/annotation/pretrained-models'),
  getActiveJob: (datasetId) =>
    http.get(`/annotation/active-job/${datasetId}`),
  batchReplaceClasses: (data) =>
    http.post('/annotation/batch-replace-classes', data),
}

// Add auto-annotate to trainingApi for convenience
trainingApi.autoAnnotate = annotationApi.autoAnnotate

// Deployment APIs
export const deploymentApi = {
  createDeployment: (data) => http.post('/deployments', data),
  listDeployments: (params) => http.get('/deployments', { params }),
  getDeployment: (id) => http.get(`/deployments/${id}`),
  stopDeployment: (id) => http.post(`/deployments/${id}/stop`),
  restartDeployment: (id) => http.post(`/deployments/${id}/restart`),
  deleteDeployment: (id) => http.delete(`/deployments/${id}`),
  predict: (deploymentId, formData, params) =>
    http.post(`/deployments/${deploymentId}/predict`, formData, {
      params,
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
}

// Collection APIs
export const collectionApi = {
  clientUpload: (formData, token) =>
    http.post('/collect/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
        'X-Api-Token': token,
      },
    }),
  listDatasets: (token) =>
    http.get('/collect/datasets', {
      headers: { 'X-Api-Token': token },
    }),
}

// Validation APIs
export const validationApi = {
  validateModels: (formData) =>
    http.post('/validation/validate', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
  getHistory: (modelId, limit = 20) =>
    http.get(`/validation/history/${modelId}`, { params: { limit } }),
}

// System APIs
export const systemApi = {
  getInfo: () => http.get('/system/info'),
}
