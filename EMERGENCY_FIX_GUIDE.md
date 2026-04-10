# _connect_mcp 方法的正确代码

```python
async def _connect_mcp(self) -> None:
    """Connect to configured MCP servers (one-time, lazy).

    Fix #5: Add exponential backoff for connection retries
    """
    if self._mcp_connected or self._mcp_connecting or not self._mcp_servers:
        return
    self._mcp_connecting = True
    from nanobot.agent.tools.mcp import connect_mcp_servers

    # Fix #5: Exponential backoff parameters
    max_retries = 3
    base_delay = 1.0  # seconds
    max_delay = 30.0  # seconds

    try:
        for attempt in range(max_retries):
            try:
                self._mcp_stack = AsyncExitStack()
                await self._mcp_stack.__aenter__()
                await connect_mcp_servers(self._mcp_servers, self.tools, self._mcp_stack)
                self._mcp_connected = True
                logger.info("MCP servers connected successfully")
                break  # Success, exit retry loop
            except BaseException as e:
                logger.error("Failed to connect MCP servers (attempt {}/{}): {}", attempt + 1, max_retries, e)
                if self._mcp_stack:
                    try:
                        await self._mcp_stack.aclose()
                    except Exception:
                        pass
                    self._mcp_stack = None

                # Don't retry on last attempt
                if attempt < max_retries - 1:
                    # Calculate delay with exponential backoff + jitter
                    import random
                    delay = min(base_delay * (2 ** attempt) + random.uniform(0, 1), max_delay)
                    logger.warning("Retrying MCP connection in {:.1f} seconds...", delay)
                    await asyncio.sleep(delay)
    finally:
        self._mcp_connecting = False

    if not self._mcp_connected:
        logger.error("MCP connection failed after {} attempts", max_retries)
```

## 关键修复点

1. **添加外层 `try:`**：第 271 行前添加 `try:`，包裹整个 `for` 循环
2. **修复缩进**：
   - `for attempt in range(max_retries):` 缩进 12 空格（在 `try:` 内部）
   - `try:` (内层) 缩进 16 空格
   - `self._mcp_stack = AsyncExitStack()` 缩进 20 空格
   - `except BaseException as e:` 缩进 16 空格
   - `finally:` 缩进 8 空格（与外层 `try:` 对齐）

## 验证

修复后运行：
```bash
python -m py_compile nanobot\agent\loop.py
```

如果没有输出，说明语法正确。