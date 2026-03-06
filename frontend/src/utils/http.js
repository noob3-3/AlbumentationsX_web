import axios from 'axios'
import { ElMessage } from 'element-plus'

const http = axios.create({
  baseURL: '/api/v1',
  timeout: 600000, // 10 minutes for large file uploads
})

// Request interceptor
http.interceptors.request.use(
  (config) => config,
  (error) => Promise.reject(error),
)

// Response interceptor
http.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const msg = error.response?.data?.detail || error.response?.data?.error || error.message
    ElMessage.error(msg || '请求失败')
    return Promise.reject(error)
  },
)

export default http
