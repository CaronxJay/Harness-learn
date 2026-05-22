"""MCP Knowledge Server - 本地知识库搜索服务

基于 JSON-RPC 2.0 over stdio 协议的 MCP Server，
让 AI 工具可以搜索本地知识库中的文章。

使用方法：
    # 直接运行（通过 stdio 通信）
    python mcp_knowledge_server.py

    # 测试模式（输出调试信息）
    python mcp_knowledge_server.py --test

MCP 工具：
    - search_articles(keyword, limit=5): 按关键词搜索文章
    - get_article(article_id): 按 ID 获取文章完整内容
    - knowledge_stats(): 返回统计信息

编码规范：
    - 遵循 PEP 8
    - Google 风格 docstring
    - 只使用 Python 标准库
"""

import json
import logging
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# ============================================================
# 配置
# ============================================================

# 知识库目录
KNOWLEDGE_DIR = Path(__file__).parent / "knowledge" / "articles"
RAW_DIR = Path(__file__).parent / "knowledge" / "raw"

# 日志配置（输出到 stderr，不干扰 stdio 通信）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("mcp-knowledge-server")

# MCP 协议版本
MCP_PROTOCOL_VERSION = "2024-11-05"
MCP_SERVER_NAME = "knowledge-server"
MCP_SERVER_VERSION = "1.0.0"


# ============================================================
# 数据结构
# ============================================================

@dataclass
class Article:
    """知识条目"""
    id: str
    title: str
    source_url: str = ""
    source_type: str = ""
    summary: str = ""
    tags: list[str] = field(default_factory=list)
    tech_direction: str = ""
    quality_level: str = ""
    use_case: str = ""
    status: str = "analyzed"
    collected_at: str = ""

    def matches_keyword(self, keyword: str) -> bool:
        """检查是否匹配关键词

        Args:
            keyword: 搜索关键词

        Returns:
            是否匹配
        """
        keyword_lower = keyword.lower()
        return (
            keyword_lower in self.title.lower()
            or keyword_lower in self.summary.lower()
            or any(keyword_lower in tag.lower() for tag in self.tags)
            or keyword_lower in self.tech_direction.lower()
        )

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "title": self.title,
            "source_url": self.source_url,
            "source_type": self.source_type,
            "summary": self.summary,
            "tags": self.tags,
            "tech_direction": self.tech_direction,
            "quality_level": self.quality_level,
            "use_case": self.use_case,
            "status": self.status,
            "collected_at": self.collected_at,
        }


# ============================================================
# 知识库管理器
# ============================================================

class KnowledgeStore:
    """知识库存储管理器"""

    def __init__(self) -> None:
        """初始化知识库"""
        self.articles: dict[str, Article] = {}
        self.load_articles()

    def load_articles(self) -> None:
        """加载所有文章"""
        self.articles.clear()

        # 加载 articles 目录
        if KNOWLEDGE_DIR.exists():
            self._load_from_directory(KNOWLEDGE_DIR)

        # 如果 articles 为空，尝试加载 raw 目录
        if not self.articles and RAW_DIR.exists():
            logger.info("articles 目录为空，尝试加载 raw 目录")
            self._load_from_directory(RAW_DIR, source_fallback=True)

        logger.info(f"已加载 {len(self.articles)} 篇文章")

    def _load_from_directory(
        self,
        directory: Path,
        source_fallback: bool = False,
    ) -> None:
        """从目录加载文章

        Args:
            directory: 目录路径
            source_fallback: 是否使用 raw 数据格式
        """
        for json_file in directory.glob("*.json"):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # 处理数组格式（raw 目录）
                if isinstance(data, list):
                    for i, item in enumerate(data):
                        article = self._parse_article(
                            item,
                            fallback_id=f"{json_file.stem}-{i:03d}",
                            source_fallback=source_fallback,
                        )
                        if article:
                            self.articles[article.id] = article
                # 处理单个对象格式（articles 目录）
                elif isinstance(data, dict):
                    article = self._parse_article(data, source_fallback=source_fallback)
                    if article:
                        self.articles[article.id] = article

            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"解析失败 [{json_file.name}]: {e}")

    def _parse_article(
        self,
        data: dict[str, Any],
        fallback_id: str = "",
        source_fallback: bool = False,
    ) -> Optional[Article]:
        """解析文章数据

        Args:
            data: 文章数据字典
            fallback_id: 备用 ID
            source_fallback: 是否使用 raw 数据格式

        Returns:
            Article 对象或 None
        """
        if source_fallback:
            # raw 格式转换
            return Article(
                id=fallback_id,
                title=data.get("title", ""),
                source_url=data.get("url", ""),
                source_type=data.get("source", "unknown"),
                summary=data.get("summary", ""),
                tags=[],
                tech_direction="",
                quality_level="",
                use_case="",
                status="raw",
            )
        else:
            # articles 格式
            return Article(
                id=data.get("id", fallback_id),
                title=data.get("title", ""),
                source_url=data.get("source_url", ""),
                source_type=data.get("source_type", ""),
                summary=data.get("summary", ""),
                tags=data.get("tags", []),
                tech_direction=data.get("tech_direction", ""),
                quality_level=data.get("quality_level", ""),
                use_case=data.get("use_case", ""),
                status=data.get("status", "analyzed"),
                collected_at=data.get("collected_at", ""),
            )

    def search(self, keyword: str, limit: int = 5) -> list[Article]:
        """搜索文章

        Args:
            keyword: 搜索关键词
            limit: 返回数量限制

        Returns:
            匹配的文章列表
        """
        results = [
            article for article in self.articles.values()
            if article.matches_keyword(keyword)
        ]
        return results[:limit]

    def get_by_id(self, article_id: str) -> Optional[Article]:
        """按 ID 获取文章

        Args:
            article_id: 文章 ID

        Returns:
            Article 对象或 None
        """
        return self.articles.get(article_id)

    def get_stats(self) -> dict[str, Any]:
        """获取统计信息

        Returns:
            统计信息字典
        """
        total = len(self.articles)

        # 来源分布
        source_counter: Counter[str] = Counter()
        for article in self.articles.values():
            source_counter[article.source_type] += 1

        # 热门标签
        tag_counter: Counter[str] = Counter()
        for article in self.articles.values():
            for tag in article.tags:
                tag_counter[tag] += 1

        # 质量分布
        quality_counter: Counter[str] = Counter()
        for article in self.articles.values():
            quality_counter[article.quality_level or "未评级"] += 1

        return {
            "total_articles": total,
            "source_distribution": dict(source_counter),
            "top_tags": dict(tag_counter.most_common(10)),
            "quality_distribution": dict(quality_counter),
        }


# ============================================================
# JSON-RPC 2.0 协议
# ============================================================

@dataclass
class JSONRPCRequest:
    """JSON-RPC 2.0 请求"""
    jsonrpc: str = "2.0"
    method: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    id: Optional[int | str] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JSONRPCRequest":
        """从字典创建请求"""
        return cls(
            jsonrpc=data.get("jsonrpc", "2.0"),
            method=data.get("method", ""),
            params=data.get("params", {}),
            id=data.get("id"),
        )


@dataclass
class JSONRPCResponse:
    """JSON-RPC 2.0 响应"""
    jsonrpc: str = "2.0"
    id: Optional[int | str] = None
    result: Optional[dict[str, Any]] = None
    error: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        resp: dict[str, Any] = {"jsonrpc": self.jsonrpc, "id": self.id}
        if self.error:
            resp["error"] = self.error
        else:
            resp["result"] = self.result
        return resp

    def to_json(self) -> str:
        """转换为 JSON 字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False)


def create_error_response(
    request_id: Optional[int | str],
    code: int,
    message: str,
    data: Optional[Any] = None,
) -> JSONRPCResponse:
    """创建错误响应

    Args:
        request_id: 请求 ID
        code: 错误代码
        message: 错误消息
        data: 附加数据

    Returns:
        JSONRPCResponse 对象
    """
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return JSONRPCResponse(id=request_id, error=error)


# MCP 错误代码
ERROR_METHOD_NOT_FOUND = -32601
ERROR_INVALID_PARAMS = -32602
ERROR_INTERNAL = -32603


# ============================================================
# MCP Server
# ============================================================

class MCPServer:
    """MCP Knowledge Server"""

    def __init__(self) -> None:
        """初始化 MCP Server"""
        self.store = KnowledgeStore()
        self.initialized = False

    def handle_request(self, request_data: str) -> str:
        """处理请求

        Args:
            request_data: JSON-RPC 请求字符串

        Returns:
            JSON-RPC 响应字符串
        """
        try:
            data = json.loads(request_data)
            request = JSONRPCRequest.from_dict(data)
            logger.debug(f"收到请求: {request.method}")

            # 路由到对应的处理函数
            if request.method == "initialize":
                response = self.handle_initialize(request)
            elif request.method == "notifications/initialized":
                # 客户端确认初始化完成，无需响应
                return ""
            elif request.method == "tools/list":
                response = self.handle_tools_list(request)
            elif request.method == "tools/call":
                response = self.handle_tools_call(request)
            elif request.method == "ping":
                response = JSONRPCResponse(id=request.id, result={})
            else:
                response = create_error_response(
                    request.id,
                    ERROR_METHOD_NOT_FOUND,
                    f"未知方法: {request.method}",
                )

            return response.to_json()

        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析错误: {e}")
            response = create_error_response(None, -32700, "JSON 解析错误")
            return response.to_json()
        except Exception as e:
            logger.error(f"处理请求异常: {e}", exc_info=True)
            response = create_error_response(None, ERROR_INTERNAL, str(e))
            return response.to_json()

    def handle_initialize(self, request: JSONRPCRequest) -> JSONRPCResponse:
        """处理 initialize 请求

        Args:
            request: JSON-RPC 请求

        Returns:
            JSON-RPC 响应
        """
        self.initialized = True
        logger.info("客户端已初始化")

        result = {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {
                "tools": {},
            },
            "serverInfo": {
                "name": MCP_SERVER_NAME,
                "version": MCP_SERVER_VERSION,
            },
        }
        return JSONRPCResponse(id=request.id, result=result)

    def handle_tools_list(self, request: JSONRPCRequest) -> JSONRPCResponse:
        """处理 tools/list 请求

        Args:
            request: JSON-RPC 请求

        Returns:
            JSON-RPC 响应
        """
        tools = [
            {
                "name": "search_articles",
                "description": "按关键词搜索知识库文章。搜索范围包括标题、摘要和标签。",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "keyword": {
                            "type": "string",
                            "description": "搜索关键词",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "返回结果数量限制",
                            "default": 5,
                        },
                    },
                    "required": ["keyword"],
                },
            },
            {
                "name": "get_article",
                "description": "按 ID 获取文章的完整内容。",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "article_id": {
                            "type": "string",
                            "description": "文章 ID",
                        },
                    },
                    "required": ["article_id"],
                },
            },
            {
                "name": "knowledge_stats",
                "description": "返回知识库的统计信息，包括文章总数、来源分布和热门标签。",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
            },
        ]

        return JSONRPCResponse(id=request.id, result={"tools": tools})

    def handle_tools_call(self, request: JSONRPCRequest) -> JSONRPCResponse:
        """处理 tools/call 请求

        Args:
            request: JSON-RPC 请求

        Returns:
            JSON-RPC 响应
        """
        tool_name = request.params.get("name")
        arguments = request.params.get("arguments", {})

        logger.info(f"调用工具: {tool_name}, 参数: {arguments}")

        if tool_name == "search_articles":
            return self._handle_search_articles(request.id, arguments)
        elif tool_name == "get_article":
            return self._handle_get_article(request.id, arguments)
        elif tool_name == "knowledge_stats":
            return self._handle_knowledge_stats(request.id)
        else:
            return create_error_response(
                request.id,
                ERROR_METHOD_NOT_FOUND,
                f"未知工具: {tool_name}",
            )

    def _handle_search_articles(
        self,
        request_id: Optional[int | str],
        arguments: dict[str, Any],
    ) -> JSONRPCResponse:
        """处理 search_articles 工具调用

        Args:
            request_id: 请求 ID
            arguments: 工具参数

        Returns:
            JSON-RPC 响应
        """
        keyword = arguments.get("keyword")
        if not keyword:
            return create_error_response(
                request_id,
                ERROR_INVALID_PARAMS,
                "缺少必需参数: keyword",
            )

        limit = arguments.get("limit", 5)
        if not isinstance(limit, int) or limit < 1:
            limit = 5

        # 搜索文章
        articles = self.store.search(keyword, limit)

        # 格式化结果
        results = []
        for article in articles:
            results.append({
                "id": article.id,
                "title": article.title,
                "summary": article.summary[:200] + "..." if len(article.summary) > 200 else article.summary,
                "tags": article.tags,
                "source_type": article.source_type,
                "quality_level": article.quality_level,
            })

        content = {
            "type": "text",
            "text": json.dumps({
                "keyword": keyword,
                "total_found": len(results),
                "articles": results,
            }, ensure_ascii=False, indent=2),
        }

        return JSONRPCResponse(id=request_id, result={"content": [content]})

    def _handle_get_article(
        self,
        request_id: Optional[int | str],
        arguments: dict[str, Any],
    ) -> JSONRPCResponse:
        """处理 get_article 工具调用

        Args:
            request_id: 请求 ID
            arguments: 工具参数

        Returns:
            JSON-RPC 响应
        """
        article_id = arguments.get("article_id")
        if not article_id:
            return create_error_response(
                request_id,
                ERROR_INVALID_PARAMS,
                "缺少必需参数: article_id",
            )

        article = self.store.get_by_id(article_id)
        if not article:
            content = {
                "type": "text",
                "text": json.dumps({
                    "error": f"文章不存在: {article_id}",
                    "available_ids_sample": list(self.store.articles.keys())[:5],
                }, ensure_ascii=False),
            }
            return JSONRPCResponse(id=request_id, result={"content": [content]})

        content = {
            "type": "text",
            "text": json.dumps(article.to_dict(), ensure_ascii=False, indent=2),
        }

        return JSONRPCResponse(id=request_id, result={"content": [content]})

    def _handle_knowledge_stats(
        self,
        request_id: Optional[int | str],
    ) -> JSONRPCResponse:
        """处理 knowledge_stats 工具调用

        Args:
            request_id: 请求 ID

        Returns:
            JSON-RPC 响应
        """
        stats = self.store.get_stats()

        content = {
            "type": "text",
            "text": json.dumps(stats, ensure_ascii=False, indent=2),
        }

        return JSONRPCResponse(id=request_id, result={"content": [content]})

    def run(self) -> None:
        """运行 MCP Server（stdio 模式）"""
        logger.info(f"MCP Knowledge Server 启动")
        logger.info(f"知识库目录: {KNOWLEDGE_DIR}")
        logger.info(f"已加载文章数: {len(self.store.articles)}")

        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue

            logger.debug(f"收到: {line[:100]}...")
            response = self.handle_request(line)

            if response:
                print(response, flush=True)
                logger.debug(f"发送: {response[:100]}...")

        logger.info("MCP Server 停止")


# ============================================================
# 测试模式
# ============================================================

def test_mode() -> None:
    """测试模式：模拟 MCP 客户端请求"""
    server = MCPServer()

    print("=" * 60, file=sys.stderr)
    print("MCP Knowledge Server 测试模式", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print(f"已加载文章数: {len(server.store.articles)}", file=sys.stderr)
    print(file=sys.stderr)

    # 测试 initialize
    print("--- 测试 initialize ---", file=sys.stderr)
    request = {"jsonrpc": "2.0", "method": "initialize", "id": 1}
    response = server.handle_request(json.dumps(request))
    print(f"响应: {response}", file=sys.stderr)
    print(file=sys.stderr)

    # 测试 tools/list
    print("--- 测试 tools/list ---", file=sys.stderr)
    request = {"jsonrpc": "2.0", "method": "tools/list", "id": 2}
    response = server.handle_request(json.dumps(request))
    print(f"响应: {response}", file=sys.stderr)
    print(file=sys.stderr)

    # 测试 search_articles
    print("--- 测试 search_articles ---", file=sys.stderr)
    request = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "search_articles",
            "arguments": {"keyword": "LLM", "limit": 3},
        },
        "id": 3,
    }
    response = server.handle_request(json.dumps(request))
    print(f"响应: {response}", file=sys.stderr)
    print(file=sys.stderr)

    # 测试 knowledge_stats
    print("--- 测试 knowledge_stats ---", file=sys.stderr)
    request = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": "knowledge_stats", "arguments": {}},
        "id": 4,
    }
    response = server.handle_request(json.dumps(request))
    print(f"响应: {response}", file=sys.stderr)
    print(file=sys.stderr)

    print("测试完成", file=sys.stderr)


# ============================================================
# CLI 入口
# ============================================================

def main() -> None:
    """主函数"""
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        test_mode()
    else:
        server = MCPServer()
        server.run()


if __name__ == "__main__":
    main()
