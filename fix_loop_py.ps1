# 临时文件：提取并修复 _connect_mcp 方法
$loop_py = "C:\Users\sammi_hung\Desktop\SFC_AI\sfc_poc\nanobot\nanobot\agent\loop.py"
$content = Get-Content $loop_py -Raw

# 找到 _connect_mcp 方法的开始和结束
$start_pattern = "async def _connect_mcp\(self\) -> None:"
$end_pattern = "if not self._mcp_connected:"

$start_index = $content.IndexOf($start_pattern)
$end_index = $content.IndexOf($end_pattern, $start_index)

# 提取旧的方法
$old_method = $content.Substring($start_index, $end_index - $start_index)

# 新的方法（修复语法错误）
$new_method = @"
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
                    logger.info("✅ MCP servers connected successfully")
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
        
        "@

# 替换
$new_content = $content.Replace($old_method, $new_method)

# 写回文件
$new_content | Set-Content $loop_py -NoNewline

Write-Host "Fixed loop.py syntax error"