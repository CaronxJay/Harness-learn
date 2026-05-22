"""分析 Agent - 为原始数据打标签"""

import json
import logging
from pathlib import Path
from typing import Any

from openai import OpenAI

logger = logging.getLogger(__name__)

# 技术方向标签
TECH_DIRECTIONS = [
    "llm", "agent", "rag", "multimodal", "code-gen",
    "fine-tuning", "inference", "training", "dataset",
    "tool", "framework", "application"
]

# 质量等级
QUALITY_LEVELS = {
    "S": "9-10 改变格局",
    "A": "7-8 直接有帮助",
    "B": "5-6 值得了解",
    "C": "1-4 可略过"
}


def load_raw_data(file_path: Path) -> list[dict[str, Any]]:
    """加载原始数据文件"""
    if not file_path.exists():
        logger.warning(f"文件不存在: {file_path}")
        return []
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, list):
                logger.error(f"数据格式错误: {file_path} 不是数组")
                return []
            return data
    except json.JSONDecodeError as e:
        logger.error(f"JSON 解析错误: {file_path} - {e}")
        return []


def analyze_entry(client: OpenAI, entry: dict[str, Any]) -> dict[str, Any]:
    """分析单条数据，添加标签"""
    prompt = f"""分析以下 GitHub/Hacker News 项目，返回 JSON 格式：

项目信息：
- 标题：{entry.get('title', '未知')}
- 链接：{entry.get('url', '未知')}
- 来源：{entry.get('source', '未知')}
- 热度：{entry.get('popularity', 0)}
- 摘要：{entry.get('summary', '未知')}

请分析并返回以下字段（JSON 格式）：
1. tags: 技术标签数组，从以下选择 2-4 个：{TECH_DIRECTIONS}
2. tech_direction: 主要技术方向，从以下选择 1 个：{TECH_DIRECTIONS}
3. quality_level: 质量等级（S/A/B/C）
4. use_case: 适用场景，一句话描述谁会用、怎么用

返回格式：
{{
  "tags": ["tag1", "tag2"],
  "tech_direction": "llm",
  "quality_level": "A",
  "use_case": "开发者可以用这个工具..."
}}"""

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是一个 AI 技术分析专家，擅长分析 GitHub 和 Hacker News 上的项目。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        
        # 验证字段
        if "tags" not in result:
            result["tags"] = []
        if "tech_direction" not in result:
            result["tech_direction"] = "unknown"
        if "quality_level" not in result:
            result["quality_level"] = "C"
        if "use_case" not in result:
            result["use_case"] = "未知"
            
        return result
    except Exception as e:
        logger.error(f"分析失败: {entry.get('title', '未知')} - {e}")
        return {
            "tags": [],
            "tech_direction": "unknown",
            "quality_level": "C",
            "use_case": "分析失败"
        }


def analyze_raw_data(input_file: Path, output_file: Path) -> bool:
    """分析原始数据并保存结果"""
    # 加载原始数据
    raw_data = load_raw_data(input_file)
    if not raw_data:
        logger.warning(f"没有数据需要分析: {input_file}")
        return False
    
    logger.info(f"开始分析 {len(raw_data)} 条数据")
    
    # 初始化 OpenAI 客户端（兼容 DeepSeek）
    client = OpenAI(
        base_url="https://api.deepseek.com/v1",
        api_key=os.getenv("DEEPSEEK_API_KEY")
    )
    
    analyzed_data = []
    success_count = 0
    fail_count = 0
    
    for entry in raw_data:
        logger.info(f"分析: {entry.get('title', '未知')}")
        
        # 分析并添加标签
        tags = analyze_entry(client, entry)
        entry.update(tags)
        
        analyzed_data.append(entry)
        
        if tags.get("tech_direction") != "unknown":
            success_count += 1
        else:
            fail_count += 1
    
    # 保存结果
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(analyzed_data, f, ensure_ascii=False, indent=2)
        logger.info(f"分析完成: 成功 {success_count} 条, 失败 {fail_count} 条")
        return True
    except Exception as e:
        logger.error(f"保存失败: {output_file} - {e}")
        return False


if __name__ == "__main__":
    import os
    
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # 示例用法
    input_file = Path("knowledge/raw/2026-05-21.json")
    output_file = Path("knowledge/raw/2026-05-21-analyzed.json")
    
    if input_file.exists():
        analyze_raw_data(input_file, output_file)
    else:
        logger.error(f"输入文件不存在: {input_file}")
