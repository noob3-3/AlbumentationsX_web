"""
Webhook service for sending task notifications to external systems
支持钉钉、企业微信、飞书等平台
"""
import hmac
import hashlib
import asyncio
import base64
import time
from typing import Dict, Any, Optional
from datetime import datetime
import httpx
from loguru import logger


class WebhookService:
    """Webhook 推送服务"""

    @staticmethod
    def generate_signature(payload: str, secret: str) -> str:
        """生成 HMAC-SHA256 签名（通用格式）"""
        return hmac.new(
            secret.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

    @staticmethod
    def generate_dingtalk_signature(timestamp: str, secret: str) -> str:
        """
        生成钉钉机器人加签

        钉钉文档：https://open.dingtalk.com/document/robots/customize-robot-security-settings
        """
        # 把timestamp和secret拼接成字符串
        string_to_sign = f"{timestamp}\n{secret}"

        # 使用HmacSHA256算法计算签名
        hmac_code = hmac.new(
            secret.encode('utf-8'),
            string_to_sign.encode('utf-8'),
            digestmod=hashlib.sha256
        ).digest()

        # 对签名进行Base64编码
        sign = base64.b64encode(hmac_code).decode('utf-8')
        return sign

    @staticmethod
    def detect_webhook_type(url: str) -> str:
        """
        检测 Webhook 类型

        Returns:
            'dingtalk' | 'wecom' | 'feishu' | 'generic'
        """
        url_lower = url.lower()
        if 'dingtalk.com' in url_lower or 'oapi.dingtalk.com' in url_lower:
            return 'dingtalk'
        elif 'qyapi.weixin.qq.com' in url_lower:
            return 'wecom'  # 企业微信
        elif 'feishu.cn' in url_lower or 'larksuite.com' in url_lower:
            return 'feishu'  # 飞书
        else:
            return 'generic'

    @staticmethod
    def format_dingtalk_message(event_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        格式化钉钉消息

        钉钉支持的消息类型：text, link, markdown, actionCard, feedCard
        """
        # 提取关键信息
        job_id = data.get('job_id', 'N/A')
        name = data.get('name', '未命名任务')
        status = data.get('status', 'unknown')

        # 构建Markdown消息
        if 'training' in event_type:
            if 'started' in event_type:
                title = f"🚀 训练任务已启动"
                text = f"### {title}\n\n"
                text += f"**任务名称**: {name}\n\n"
                text += f"**任务ID**: {job_id}\n\n"
                text += f"**模型**: {data.get('model_name', 'N/A')}\n\n"
                text += f"**训练轮数**: {data.get('epochs', 'N/A')}\n\n"
                text += f"**批次大小**: {data.get('batch_size', 'N/A')}\n\n"
                text += f"**开始时间**: {data.get('started_at', 'N/A')}"
            elif 'completed' in event_type:
                title = f"✅ 训练任务已完成"
                text = f"### {title}\n\n"
                text += f"**任务名称**: {name}\n\n"
                text += f"**任务ID**: {job_id}\n\n"
                text += f"**状态**: {status}\n\n"
                map50 = data.get('best_map50')
                if map50:
                    text += f"**mAP50**: {float(map50)*100:.1f}%\n\n"
                map50_95 = data.get('best_map50_95')
                if map50_95:
                    text += f"**mAP50-95**: {float(map50_95)*100:.1f}%\n\n"
                text += f"**完成时间**: {data.get('completed_at', 'N/A')}"
            elif 'failed' in event_type:
                title = f"❌ 训练任务失败"
                text = f"### {title}\n\n"
                text += f"**任务名称**: {name}\n\n"
                text += f"**任务ID**: {job_id}\n\n"
                text += f"**错误信息**: {data.get('error', '未知错误')}\n\n"
                text += f"**失败时间**: {data.get('completed_at', 'N/A')}"
            else:
                title = f"📊 训练任务更新"
                text = f"### {title}\n\n"
                text += f"**任务**: {name}\n\n"
                text += f"**状态**: {status}"
        elif 'augmentation' in event_type:
            title = f"🎨 数据增强任务 - {status}"
            text = f"### {title}\n\n"
            text += f"**任务ID**: {job_id}\n\n"
            text += f"**事件**: {event_type}"
        elif 'annotation' in event_type:
            title = f"🏷️ 自动标注任务 - {status}"
            text = f"### {title}\n\n"
            text += f"**任务ID**: {job_id}\n\n"
            text += f"**事件**: {event_type}"
        elif event_type == 'test':
            title = "🔔 Webhook 测试消息"
            text = f"### {title}\n\n"
            text += f"**项目**: {data.get('project_name', 'N/A')}\n\n"
            text += f"**项目ID**: {data.get('project_id', 'N/A')}\n\n"
            text += f"**消息**: {data.get('message', 'This is a test')}\n\n"
            text += f"**时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        else:
            title = f"📢 系统通知"
            text = f"### {title}\n\n**事件**: {event_type}"

        return {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": text
            }
        }

    @staticmethod
    async def send_webhook(
        url: str,
        event_type: str,
        data: Dict[str, Any],
        secret: Optional[str] = None,
        timeout: int = 10
    ) -> bool:
        """
        发送 Webhook 通知（智能识别平台类型）

        Args:
            url: Webhook URL
            event_type: 事件类型
            data: 事件数据
            secret: 签名密钥（钉钉为加签密钥，通用为HMAC密钥）
            timeout: 超时时间（秒）

        Returns:
            bool: 是否发送成功
        """
        try:
            webhook_type = WebhookService.detect_webhook_type(url)
            logger.info(f"📤 Detected webhook type: {webhook_type}")

            headers = {
                "Content-Type": "application/json",
                "User-Agent": "AlbumentationsX-Webhook/1.0"
            }

            # 根据不同平台构建不同的消息格式
            if webhook_type == 'dingtalk':
                # 钉钉格式
                payload = WebhookService.format_dingtalk_message(event_type, data)

                # 如果有加签密钥，添加签名参数到URL
                if secret:
                    timestamp = str(round(time.time() * 1000))
                    sign = WebhookService.generate_dingtalk_signature(timestamp, secret)

                    # 钉钉需要在URL中添加timestamp和sign参数
                    separator = '&' if '?' in url else '?'
                    url = f"{url}{separator}timestamp={timestamp}&sign={sign}"
                    logger.info(f"🔐 DingTalk signature added")

            elif webhook_type == 'wecom':
                # 企业微信格式（类似钉钉）
                payload = WebhookService.format_dingtalk_message(event_type, data)

            elif webhook_type == 'feishu':
                # 飞书格式（需要调整）
                dingtalk_format = WebhookService.format_dingtalk_message(event_type, data)
                # 飞书使用不同的字段名
                payload = {
                    "msg_type": "interactive",
                    "card": {
                        "header": {
                            "title": {
                                "content": dingtalk_format['markdown']['title'],
                                "tag": "plain_text"
                            }
                        },
                        "elements": [
                            {
                                "tag": "markdown",
                                "content": dingtalk_format['markdown']['text']
                            }
                        ]
                    }
                }
            else:
                # 通用格式（原有格式）
                payload = {
                    "event": event_type,
                    "timestamp": datetime.utcnow().isoformat(),
                    "data": data
                }

                # 通用格式的HMAC签名
                if secret:
                    import json
                    payload_str = json.dumps(payload, ensure_ascii=False)
                    signature = WebhookService.generate_signature(payload_str, secret)
                    headers["X-Webhook-Signature"] = f"sha256={signature}"

            logger.info(f"📤 Sending webhook: {event_type} to {webhook_type} ({url[:50]}...)")

            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers=headers
                )

                if response.status_code >= 200 and response.status_code < 300:
                    logger.info(f"✅ Webhook sent successfully: {event_type}")

                    # 检查钉钉的响应
                    if webhook_type == 'dingtalk':
                        try:
                            resp_data = response.json()
                            if resp_data.get('errcode') == 0:
                                logger.info(f"✅ DingTalk robot confirmed: {resp_data.get('errmsg', 'ok')}")
                            else:
                                logger.warning(f"⚠️ DingTalk response: {resp_data}")
                        except:
                            pass

                    return True
                else:
                    logger.warning(f"⚠️ Webhook failed with status {response.status_code}: {response.text[:200]}")
                    return False

        except asyncio.TimeoutError:
            logger.error(f"❌ Webhook timeout: {url}")
            return False
        except Exception as e:
            logger.error(f"❌ Webhook error: {e}")
            return False

    @staticmethod
    async def send_training_webhook(
        webhook_url: str,
        event_type: str,
        job_data: Dict[str, Any],
        secret: Optional[str] = None
    ):
        """发送训练任务 Webhook"""
        await WebhookService.send_webhook(
            url=webhook_url,
            event_type=f"training.{event_type}",
            data=job_data,
            secret=secret
        )

    @staticmethod
    async def send_augmentation_webhook(
        webhook_url: str,
        event_type: str,
        job_data: Dict[str, Any],
        secret: Optional[str] = None
    ):
        """发送数据增强任务 Webhook"""
        await WebhookService.send_webhook(
            url=webhook_url,
            event_type=f"augmentation.{event_type}",
            data=job_data,
            secret=secret
        )

    @staticmethod
    async def send_annotation_webhook(
        webhook_url: str,
        event_type: str,
        job_data: Dict[str, Any],
        secret: Optional[str] = None
    ):
        """发送标注任务 Webhook"""
        await WebhookService.send_webhook(
            url=webhook_url,
            event_type=f"annotation.{event_type}",
            data=job_data,
            secret=secret
        )

    @staticmethod
    def format_training_data(job) -> Dict[str, Any]:
        """格式化训练任务数据"""
        return {
            "job_id": job.id,
            "name": job.name,
            "status": job.status.value if hasattr(job.status, 'value') else job.status,
            "dataset_id": job.dataset_id,
            "model_name": job.model_name,
            "epochs": job.epochs,
            "current_epoch": job.current_epoch,
            "batch_size": job.batch_size,
            "best_map50": job.best_map50,
            "best_map50_95": job.best_map50_95,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "error_message": job.error_message,
        }

    @staticmethod
    def format_augmentation_data(job) -> Dict[str, Any]:
        """格式化数据增强任务数据"""
        return {
            "job_id": job.id,
            "dataset_id": job.dataset_id,
            "status": job.status.value if hasattr(job.status, 'value') else job.status,
            "augmented_count": job.augmented_count,
            "target_count": job.target_count,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "error_message": job.error_message,
        }


webhook_service = WebhookService()

