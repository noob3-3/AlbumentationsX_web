# 客户端 API

![客户端 API](/screenshots/10-client-api.png)

现场脚本或采集端可通过 HTTP 把图片推送到指定数据集。

1. 页面展示 **服务器地址** 和 **API Token**，请复制使用，不要把 Token 提交到公开仓库。
2. 生产环境请在服务端把 `CLIENT_API_TOKEN` 配成强随机字符串。
3. **在线测试**：选择目标数据集和测试图片后点 **测试上传**，确认链路正常。
4. **代码示例** 支持 Python / cURL / JavaScript。请求需带 **`X-Api-Token`** 请求头；示例中的 `API_BASE`、`dataset_id` 请换成实际环境。
