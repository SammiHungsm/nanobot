#!/usr/bin/env python3
"""Fix loop.py syntax error"""

with open('nanobot/agent/loop.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 找到问题代码块并替换
old_code = '''        for attempt in range(max_retries):
            try:
                self._mcp_stack = AsyncExitStack()
                await self._mcp_stack.__aenter__()
                await connect_mcp_servers(self._mcp_servers, self.tools, self._mcp_stack)
                self._mcp_connected = True
                logger.info("??MCP servers connected successfully")
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
            self._mcp_connecting = False'''

new_code = '''        try:
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
            self._mcp_connecting = False'''

# 替换
new_content = content.replace(old_code, new_code)

# 写回
with open('nanobot/agent/loop.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print('[OK] Fixed loop.py syntax error')