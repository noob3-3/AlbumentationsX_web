"""
Augmentation transforms with Chinese descriptions and parameter definitions
Based on https://albumentations.ai/docs/
"""
from typing import Dict, Any, List

# 增强变换的中文信息和参数定义
TRANSFORM_INFO = {
    # ===== 几何变换 (Geometric) =====
    "HorizontalFlip": {
        "category": "geometric",
        "name_zh": "水平翻转",
        "description": "以50%概率水平翻转图像和标注框",
        "params": {
            "p": {"type": "float", "default": 0.5, "min": 0.0, "max": 1.0, "label": "概率"}
        }
    },
    "VerticalFlip": {
        "category": "geometric",
        "name_zh": "垂直翻转",
        "description": "以指定概率垂直翻转图像和标注框",
        "params": {
            "p": {"type": "float", "default": 0.2, "min": 0.0, "max": 1.0, "label": "概率"}
        }
    },
    "RandomRotate90": {
        "category": "geometric",
        "name_zh": "随机90度旋转",
        "description": "随机旋转90、180或270度",
        "params": {
            "p": {"type": "float", "default": 0.3, "min": 0.0, "max": 1.0, "label": "概率"}
        }
    },
    "Rotate": {
        "category": "geometric",
        "name_zh": "旋转",
        "description": "在指定角度范围内随机旋转",
        "params": {
            "limit": {"type": "range", "default": [-15, 15], "min": -180, "max": 180, "label": "角度范围"},
            "p": {"type": "float", "default": 0.5, "min": 0.0, "max": 1.0, "label": "概率"}
        }
    },
    "Affine": {
        "category": "geometric",
        "name_zh": "仿射变换",
        "description": "组合平移、缩放和旋转的仿射变换",
        "params": {
            "scale": {"type": "range", "default": [0.8, 1.2], "min": 0.1, "max": 2.0, "label": "缩放范围"},
            "translate_percent_x": {"type": "range", "default": [-0.1, 0.1], "min": -0.5, "max": 0.5, "label": "水平平移比例"},
            "translate_percent_y": {"type": "range", "default": [-0.1, 0.1], "min": -0.5, "max": 0.5, "label": "垂直平移比例"},
            "rotate": {"type": "range", "default": [-15, 15], "min": -180, "max": 180, "label": "旋转角度"},
            "p": {"type": "float", "default": 0.5, "min": 0.0, "max": 1.0, "label": "概率"}
        }
    },
    "Perspective": {
        "category": "geometric",
        "name_zh": "透视变换",
        "description": "随机透视变换，模拟不同视角",
        "params": {
            "scale": {"type": "range", "default": [0.05, 0.1], "min": 0.0, "max": 0.3, "label": "变换强度"},
            "p": {"type": "float", "default": 0.3, "min": 0.0, "max": 1.0, "label": "概率"}
        }
    },
    "ElasticTransform": {
        "category": "geometric",
        "name_zh": "弹性变换",
        "description": "局部扭曲变形，增加样本多样性",
        "params": {
            "alpha": {"type": "float", "default": 1.0, "min": 0.0, "max": 10.0, "label": "变形强度"},
            "sigma": {"type": "float", "default": 50.0, "min": 1.0, "max": 100.0, "label": "平滑度"},
            "p": {"type": "float", "default": 0.2, "min": 0.0, "max": 1.0, "label": "概率"}
        }
    },
    "GridDistortion": {
        "category": "geometric",
        "name_zh": "网格扭曲",
        "description": "基于网格的扭曲变换",
        "params": {
            "num_steps": {"type": "int", "default": 5, "min": 1, "max": 20, "label": "网格步数"},
            "distort_limit": {"type": "float", "default": 0.3, "min": 0.0, "max": 1.0, "label": "扭曲强度"},
            "p": {"type": "float", "default": 0.2, "min": 0.0, "max": 1.0, "label": "概率"}
        }
    },
    "OpticalDistortion": {
        "category": "geometric",
        "name_zh": "光学畸变",
        "description": "模拟镜头畸变效果",
        "params": {
            "distort_limit": {"type": "float", "default": 0.3, "min": 0.0, "max": 1.0, "label": "畸变强度"},
            "shift_limit": {"type": "float", "default": 0.05, "min": 0.0, "max": 0.5, "label": "偏移强度"},
            "p": {"type": "float", "default": 0.2, "min": 0.0, "max": 1.0, "label": "概率"}
        }
    },
    "Transpose": {
        "category": "geometric",
        "name_zh": "转置",
        "description": "交换图像的宽高（90度旋转+翻转）",
        "params": {
            "p": {"type": "float", "default": 0.3, "min": 0.0, "max": 1.0, "label": "概率"}
        }
    },

    # ===== 裁剪和缩放 (Crop & Resize) =====
    "RandomResizedCrop": {
        "category": "crop",
        "name_zh": "随机裁剪缩放",
        "description": "随机裁剪并调整到指定大小，常用于训练",
        "params": {
            "height": {"type": "int", "default": 640, "min": 32, "max": 1920, "label": "目标高度"},
            "width": {"type": "int", "default": 640, "min": 32, "max": 1920, "label": "目标宽度"},
            "scale": {"type": "range", "default": [0.7, 1.0], "min": 0.1, "max": 1.0, "label": "缩放比例"},
            "p": {"type": "float", "default": 0.4, "min": 0.0, "max": 1.0, "label": "概率"}
        }
    },
    "RandomCrop": {
        "category": "crop",
        "name_zh": "随机裁剪",
        "description": "随机裁剪固定大小区域",
        "params": {
            "height": {"type": "int", "default": 512, "min": 32, "max": 1920, "label": "裁剪高度"},
            "width": {"type": "int", "default": 512, "min": 32, "max": 1920, "label": "裁剪宽度"},
            "p": {"type": "float", "default": 0.3, "min": 0.0, "max": 1.0, "label": "概率"}
        }
    },
    "CenterCrop": {
        "category": "crop",
        "name_zh": "中心裁剪",
        "description": "从图像中心裁剪固定大小区域",
        "params": {
            "height": {"type": "int", "default": 512, "min": 32, "max": 1920, "label": "裁剪高度"},
            "width": {"type": "int", "default": 512, "min": 32, "max": 1920, "label": "裁剪宽度"},
            "p": {"type": "float", "default": 0.2, "min": 0.0, "max": 1.0, "label": "概率"}
        }
    },

    # ===== 颜色变换 (Color) =====
    "RandomBrightnessContrast": {
        "category": "color",
        "name_zh": "随机亮度对比度",
        "description": "随机调整亮度和对比度，模拟不同光照",
        "params": {
            "brightness_limit": {"type": "float", "default": 0.3, "min": 0.0, "max": 1.0, "label": "亮度范围"},
            "contrast_limit": {"type": "float", "default": 0.3, "min": 0.0, "max": 1.0, "label": "对比度范围"},
            "p": {"type": "float", "default": 0.5, "min": 0.0, "max": 1.0, "label": "概率"}
        }
    },
    "HueSaturationValue": {
        "category": "color",
        "name_zh": "色调饱和度亮度",
        "description": "调整色调、饱和度和亮度值",
        "params": {
            "hue_shift_limit": {"type": "int", "default": 20, "min": 0, "max": 180, "label": "色调偏移"},
            "sat_shift_limit": {"type": "int", "default": 30, "min": 0, "max": 100, "label": "饱和度偏移"},
            "val_shift_limit": {"type": "int", "default": 20, "min": 0, "max": 100, "label": "亮度偏移"},
            "p": {"type": "float", "default": 0.4, "min": 0.0, "max": 1.0, "label": "概率"}
        }
    },
    "RGBShift": {
        "category": "color",
        "name_zh": "RGB偏移",
        "description": "独立调整RGB三个通道的值",
        "params": {
            "r_shift_limit": {"type": "int", "default": 20, "min": 0, "max": 100, "label": "红色偏移"},
            "g_shift_limit": {"type": "int", "default": 20, "min": 0, "max": 100, "label": "绿色偏移"},
            "b_shift_limit": {"type": "int", "default": 20, "min": 0, "max": 100, "label": "蓝色偏移"},
            "p": {"type": "float", "default": 0.3, "min": 0.0, "max": 1.0, "label": "概率"}
        }
    },
    "ChannelShuffle": {
        "category": "color",
        "name_zh": "通道打乱",
        "description": "随机打乱RGB通道顺序",
        "params": {
            "p": {"type": "float", "default": 0.2, "min": 0.0, "max": 1.0, "label": "概率"}
        }
    },
    "ToGray": {
        "category": "color",
        "name_zh": "转灰度",
        "description": "将图像转换为灰度图",
        "params": {
            "p": {"type": "float", "default": 0.1, "min": 0.0, "max": 1.0, "label": "概率"}
        }
    },
    "ColorJitter": {
        "category": "color",
        "name_zh": "颜色抖动",
        "description": "组合调整亮度、对比度、饱和度和色调",
        "params": {
            "brightness": {"type": "float", "default": 0.2, "min": 0.0, "max": 1.0, "label": "亮度"},
            "contrast": {"type": "float", "default": 0.2, "min": 0.0, "max": 1.0, "label": "对比度"},
            "saturation": {"type": "float", "default": 0.2, "min": 0.0, "max": 1.0, "label": "饱和度"},
            "hue": {"type": "float", "default": 0.1, "min": 0.0, "max": 0.5, "label": "色调"},
            "p": {"type": "float", "default": 0.4, "min": 0.0, "max": 1.0, "label": "概率"}
        }
    },

    # ===== 图像质量 (Quality) =====
    "CLAHE": {
        "category": "quality",
        "name_zh": "对比度受限自适应直方图均衡",
        "description": "增强局部对比度，改善暗光图像",
        "params": {
            "clip_limit": {"type": "float", "default": 4.0, "min": 1.0, "max": 10.0, "label": "裁剪限制"},
            "tile_grid_size": {"type": "int", "default": 8, "min": 2, "max": 16, "label": "网格大小"},
            "p": {"type": "float", "default": 0.3, "min": 0.0, "max": 1.0, "label": "概率"}
        }
    },
    "Equalize": {
        "category": "quality",
        "name_zh": "直方图均衡",
        "description": "均衡化图像直方图，增强对比度",
        "params": {
            "p": {"type": "float", "default": 0.2, "min": 0.0, "max": 1.0, "label": "概率"}
        }
    },
    "Sharpen": {
        "category": "quality",
        "name_zh": "锐化",
        "description": "增强图像边缘和细节",
        "params": {
            "alpha": {"type": "range", "default": [0.2, 0.5], "min": 0.0, "max": 1.0, "label": "强度"},
            "lightness": {"type": "range", "default": [0.5, 1.0], "min": 0.0, "max": 1.0, "label": "亮度"},
            "p": {"type": "float", "default": 0.3, "min": 0.0, "max": 1.0, "label": "概率"}
        }
    },
    "Posterize": {
        "category": "quality",
        "name_zh": "色调分离",
        "description": "减少颜色位数，产生海报效果",
        "params": {
            "num_bits": {"type": "int", "default": 4, "min": 1, "max": 8, "label": "位数"},
            "p": {"type": "float", "default": 0.2, "min": 0.0, "max": 1.0, "label": "概率"}
        }
    },
    "Solarize": {
        "category": "quality",
        "name_zh": "曝光过度",
        "description": "反转超过阈值的像素值",
        "params": {
            "threshold": {"type": "int", "default": 128, "min": 0, "max": 255, "label": "阈值"},
            "p": {"type": "float", "default": 0.2, "min": 0.0, "max": 1.0, "label": "概率"}
        }
    },
    "Emboss": {
        "category": "quality",
        "name_zh": "浮雕",
        "description": "产生浮雕效果",
        "params": {
            "alpha": {"type": "range", "default": [0.2, 0.5], "min": 0.0, "max": 1.0, "label": "强度"},
            "strength": {"type": "range", "default": [0.2, 0.7], "min": 0.0, "max": 1.0, "label": "力度"},
            "p": {"type": "float", "default": 0.2, "min": 0.0, "max": 1.0, "label": "概率"}
        }
    },

    # ===== 模糊 (Blur) =====
    "GaussianBlur": {
        "category": "blur",
        "name_zh": "高斯模糊",
        "description": "应用高斯模糊，模拟失焦效果",
        "params": {
            "blur_limit": {"type": "range", "default": [3, 7], "min": 3, "max": 15, "label": "模糊核大小"},
            "p": {"type": "float", "default": 0.3, "min": 0.0, "max": 1.0, "label": "概率"}
        }
    },
    "MotionBlur": {
        "category": "blur",
        "name_zh": "运动模糊",
        "description": "模拟相机或物体运动造成的模糊",
        "params": {
            "blur_limit": {"type": "int", "default": 7, "min": 3, "max": 15, "label": "模糊强度"},
            "p": {"type": "float", "default": 0.3, "min": 0.0, "max": 1.0, "label": "概率"}
        }
    },
    "MedianBlur": {
        "category": "blur",
        "name_zh": "中值模糊",
        "description": "应用中值滤波，去除椒盐噪声",
        "params": {
            "blur_limit": {"type": "int", "default": 5, "min": 3, "max": 15, "label": "核大小"},
            "p": {"type": "float", "default": 0.2, "min": 0.0, "max": 1.0, "label": "概率"}
        }
    },
    "Defocus": {
        "category": "blur",
        "name_zh": "散焦模糊",
        "description": "模拟镜头散焦效果",
        "params": {
            "radius": {"type": "range", "default": [3, 10], "min": 1, "max": 20, "label": "半径"},
            "alias_blur": {"type": "range", "default": [0.1, 0.5], "min": 0.0, "max": 1.0, "label": "混叠模糊"},
            "p": {"type": "float", "default": 0.2, "min": 0.0, "max": 1.0, "label": "概率"}
        }
    },

    # ===== 噪声 (Noise) =====
    "GaussNoise": {
        "category": "noise",
        "name_zh": "高斯噪声",
        "description": "添加高斯噪声",
        "params": {
            "var_limit": {"type": "range", "default": [10.0, 50.0], "min": 0.0, "max": 200.0, "label": "方差范围"},
            "p": {"type": "float", "default": 0.3, "min": 0.0, "max": 1.0, "label": "概率"}
        }
    },
    "ISONoise": {
        "category": "noise",
        "name_zh": "ISO噪声",
        "description": "模拟相机高ISO噪声",
        "params": {
            "color_shift": {"type": "range", "default": [0.01, 0.05], "min": 0.0, "max": 0.2, "label": "颜色偏移"},
            "intensity": {"type": "range", "default": [0.1, 0.5], "min": 0.0, "max": 1.0, "label": "强度"},
            "p": {"type": "float", "default": 0.3, "min": 0.0, "max": 1.0, "label": "概率"}
        }
    },
    "MultiplicativeNoise": {
        "category": "noise",
        "name_zh": "乘性噪声",
        "description": "添加乘性噪声（斑点噪声）",
        "params": {
            "multiplier": {"type": "range", "default": [0.9, 1.1], "min": 0.5, "max": 1.5, "label": "乘数"},
            "p": {"type": "float", "default": 0.2, "min": 0.0, "max": 1.0, "label": "概率"}
        }
    },

    # ===== 天气和光照 (Weather & Lighting) =====
    "RandomShadow": {
        "category": "weather",
        "name_zh": "随机阴影",
        "description": "添加随机阴影效果",
        "params": {
            "shadow_roi": {"type": "range", "default": [0.0, 1.0], "min": 0.0, "max": 1.0, "label": "阴影区域"},
            "num_shadows_limit": {"type": "range", "default": [1, 2], "min": 1, "max": 5, "label": "阴影数量"},
            "p": {"type": "float", "default": 0.2, "min": 0.0, "max": 1.0, "label": "概率"}
        }
    },
    "RandomFog": {
        "category": "weather",
        "name_zh": "随机雾效",
        "description": "添加雾气效果",
        "params": {
            "fog_coef_lower": {"type": "float", "default": 0.3, "min": 0.0, "max": 1.0, "label": "最小系数"},
            "fog_coef_upper": {"type": "float", "default": 0.8, "min": 0.0, "max": 1.0, "label": "最大系数"},
            "p": {"type": "float", "default": 0.1, "min": 0.0, "max": 1.0, "label": "概率"}
        }
    },
    "RandomRain": {
        "category": "weather",
        "name_zh": "随机雨效",
        "description": "添加雨滴效果",
        "params": {
            "slant_lower": {"type": "int", "default": -10, "min": -20, "max": 0, "label": "最小倾斜"},
            "slant_upper": {"type": "int", "default": 10, "min": 0, "max": 20, "label": "最大倾斜"},
            "p": {"type": "float", "default": 0.1, "min": 0.0, "max": 1.0, "label": "概率"}
        }
    },
    "RandomSnow": {
        "category": "weather",
        "name_zh": "随机雪效",
        "description": "添加雪花效果",
        "params": {
            "snow_point_lower": {"type": "float", "default": 0.1, "min": 0.0, "max": 0.5, "label": "最小强度"},
            "snow_point_upper": {"type": "float", "default": 0.3, "min": 0.0, "max": 1.0, "label": "最大强度"},
            "p": {"type": "float", "default": 0.1, "min": 0.0, "max": 1.0, "label": "概率"}
        }
    },
    "RandomSunFlare": {
        "category": "weather",
        "name_zh": "随机太阳耀斑",
        "description": "添加镜头耀斑效果",
        "params": {
            "flare_roi": {"type": "range", "default": [0.0, 0.5], "min": 0.0, "max": 1.0, "label": "耀斑区域"},
            "src_radius": {"type": "int", "default": 100, "min": 50, "max": 200, "label": "源半径"},
            "p": {"type": "float", "default": 0.1, "min": 0.0, "max": 1.0, "label": "概率"}
        }
    },

    # ===== 像素级操作 (Pixel) =====
    "CoarseDropout": {
        "category": "pixel",
        "name_zh": "粗粒度丢弃",
        "description": "随机遮挡矩形区域，类似Cutout",
        "params": {
            "max_holes": {"type": "int", "default": 8, "min": 1, "max": 20, "label": "最大数量"},
            "max_height": {"type": "int", "default": 32, "min": 8, "max": 128, "label": "最大高度"},
            "max_width": {"type": "int", "default": 32, "min": 8, "max": 128, "label": "最大宽度"},
            "p": {"type": "float", "default": 0.3, "min": 0.0, "max": 1.0, "label": "概率"}
        }
    },
    "Superpixels": {
        "category": "pixel",
        "name_zh": "超像素",
        "description": "将图像转换为超像素表示",
        "params": {
            "p_replace": {"type": "float", "default": 0.1, "min": 0.0, "max": 1.0, "label": "替换概率"},
            "n_segments": {"type": "int", "default": 100, "min": 50, "max": 500, "label": "分段数"},
            "p": {"type": "float", "default": 0.1, "min": 0.0, "max": 1.0, "label": "概率"}
        }
    },
}

# 按类别分组
TRANSFORM_CATEGORIES = {
    "geometric": "几何变换",
    "crop": "裁剪缩放",
    "color": "颜色变换",
    "quality": "图像质量",
    "blur": "模糊效果",
    "noise": "噪声",
    "weather": "天气光照",
    "pixel": "像素操作",
}

# 默认推荐配置（针对目标检测）
RECOMMENDED_CONFIGS = {
    "light": {
        "name": "轻度增强",
        "description": "适合高质量数据集，保持图像原貌",
        "transforms": [
            {"name": "HorizontalFlip", "params": {"p": 0.5}},
            {"name": "RandomBrightnessContrast", "params": {"brightness_limit": 0.2, "contrast_limit": 0.2, "p": 0.4}},
            {"name": "GaussianBlur", "params": {"blur_limit": [3, 5], "p": 0.2}},
        ]
    },
    "medium": {
        "name": "中度增强",
        "description": "平衡增强，适合大多数场景",
        "transforms": [
            {"name": "HorizontalFlip", "params": {"p": 0.5}},
            {"name": "VerticalFlip", "params": {"p": 0.2}},
            {"name": "RandomRotate90", "params": {"p": 0.3}},
            {"name": "Affine", "params": {"translate_percent": {"x": [-0.1, 0.1], "y": [-0.1, 0.1]}, "scale": [0.8, 1.2], "rotate": [-15, 15], "p": 0.5}},
            {"name": "RandomBrightnessContrast", "params": {"brightness_limit": 0.3, "contrast_limit": 0.3, "p": 0.5}},
            {"name": "HueSaturationValue", "params": {"hue_shift_limit": 20, "sat_shift_limit": 30, "val_shift_limit": 20, "p": 0.4}},
            {"name": "GaussianBlur", "params": {"blur_limit": [3, 7], "p": 0.3}},
            {"name": "GaussNoise", "params": {"p": 0.3}},
            {"name": "CLAHE", "params": {"p": 0.3}},
            {"name": "CoarseDropout", "params": {"max_holes": 8, "max_height": 32, "max_width": 32, "p": 0.3}},
        ]
    },
    "strong": {
        "name": "强度增强",
        "description": "激进增强，适合小数据集或需要高鲁棒性",
        "transforms": [
            {"name": "HorizontalFlip", "params": {"p": 0.5}},
            {"name": "VerticalFlip", "params": {"p": 0.3}},
            {"name": "RandomRotate90", "params": {"p": 0.4}},
            {"name": "Affine", "params": {"translate_percent": {"x": [-0.2, 0.2], "y": [-0.2, 0.2]}, "scale": [0.7, 1.3], "rotate": [-30, 30], "p": 0.6}},
            {"name": "Perspective", "params": {"scale": [0.05, 0.15], "p": 0.4}},
            {"name": "RandomBrightnessContrast", "params": {"brightness_limit": 0.4, "contrast_limit": 0.4, "p": 0.6}},
            {"name": "HueSaturationValue", "params": {"hue_shift_limit": 30, "sat_shift_limit": 40, "val_shift_limit": 30, "p": 0.5}},
            {"name": "GaussianBlur", "params": {"blur_limit": [3, 9], "p": 0.4}},
            {"name": "GaussNoise", "params": {"p": 0.4}},
            {"name": "CLAHE", "params": {"p": 0.4}},
            {"name": "RandomShadow", "params": {"p": 0.3}},
            {"name": "RandomFog", "params": {"p": 0.2}},
            {"name": "CoarseDropout", "params": {"max_holes": 12, "max_height": 48, "max_width": 48, "p": 0.4}},
            {"name": "RandomResizedCrop", "params": {"height": 640, "width": 640, "scale": [0.6, 1.0], "p": 0.5}},
        ]
    },
    "classification": {
        "name": "图像分类专用",
        "description": "适合图像分类任务，不影响标注框",
        "transforms": [
            {"name": "HorizontalFlip", "params": {"p": 0.5}},
            {"name": "RandomRotate90", "params": {"p": 0.3}},
            {"name": "Rotate", "params": {"limit": [-20, 20], "p": 0.4}},
            {"name": "RandomBrightnessContrast", "params": {"brightness_limit": 0.3, "contrast_limit": 0.3, "p": 0.5}},
            {"name": "HueSaturationValue", "params": {"hue_shift_limit": 20, "sat_shift_limit": 30, "val_shift_limit": 20, "p": 0.4}},
            {"name": "CLAHE", "params": {"p": 0.3}},
            {"name": "GaussianBlur", "params": {"blur_limit": [3, 7], "p": 0.3}},
            {"name": "CoarseDropout", "params": {"max_holes": 8, "max_height": 32, "max_width": 32, "p": 0.3}},
            {"name": "RandomResizedCrop", "params": {"height": 640, "width": 640, "scale": [0.8, 1.0], "p": 0.5}},
        ]
    },
}


def get_transform_info(transform_name: str) -> Dict[str, Any]:
    """获取变换的详细信息"""
    return TRANSFORM_INFO.get(transform_name, {})


def get_transforms_by_category() -> Dict[str, List[str]]:
    """按类别获取变换列表"""
    result = {}
    for transform_name, info in TRANSFORM_INFO.items():
        category = info.get("category", "other")
        if category not in result:
            result[category] = []
        result[category].append(transform_name)
    return result


def get_recommended_config(config_name: str) -> Dict[str, Any]:
    """获取推荐配置"""
    return RECOMMENDED_CONFIGS.get(config_name, RECOMMENDED_CONFIGS["medium"])

