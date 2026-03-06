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
  uploadImagesWithLabels: (datasetId, formData, onProgress) =>
    http.post(`/datasets/${datasetId}/images/upload-with-labels`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: onProgress,
      timeout: 600000, // 10 minutes for large batch uploads
    }),
  collectFromUrls: (datasetId, data) =>
    http.post(`/datasets/${datasetId}/images/collect-from-urls`, data),
  listImages: (datasetId, params) =>
    http.get(`/datasets/${datasetId}/images`, { params }),
  getImage: (datasetId, imageId) =>
    http.get(`/datasets/${datasetId}/images/${imageId}`),
  deleteImage: (datasetId, imageId) =>
    http.delete(`/datasets/${datasetId}/images/${imageId}`),

  // 数据集统计
  getStats: (datasetId) => http.get(`/datasets/${datasetId}/stats`),

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
  availableModels: () => http.get('/training/available-models'),

  // Models
  listModels: (params) => http.get('/training/models', { params }),
  getModel: (id) => http.get(`/training/models/${id}`),
  downloadModel: (id) => `/api/v1/training/models/${id}/download`,
  downloadModelPackage: (id) => `/api/v1/training/models/${id}/download-package`,
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
