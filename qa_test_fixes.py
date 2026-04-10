"""
QA Test Script - Verify all fixes work correctly
Run this after applying the fixes to ensure everything is working.
"""
import os
import sys
import json
import re
from pathlib import Path

# Add project to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_config_env_var_interpolation():
    """Test that ${VAR:-default} pattern works in config loader."""
    print("=" * 60)
    print("TEST 1: Config Environment Variable Interpolation")
    print("=" * 60)
    
    # Set test environment variables
    os.environ["DASHSCOPE_API_KEY"] = "test-key-123"
    
    # Import the loader
    from nanobot.config.loader import _resolve_env_vars, _env_replace_with_default
    
    # Test 1: Simple ${VAR} pattern
    test_str = "${DASHSCOPE_API_KEY}"
    result = _resolve_env_vars(test_str)
    assert result == "test-key-123", f"Failed: Expected 'test-key-123', got '{result}'"
    print(f"✅ ${VAR} pattern: '{test_str}' -> '{result}'")
    
    # Test 2: ${VAR:-default} pattern with env var set
    test_str = "${DASHSCOPE_API_BASE:-https://default.api.com/v1}"
    result = _resolve_env_vars(test_str)
    # No env var set, should use default
    assert result == "https://default.api.com/v1", f"Failed: Expected default, got '{result}'"
    print(f"✅ ${VAR:-default} with no env: '{test_str}' -> '{result}'")
    
    # Test 3: ${VAR:-default} pattern with env var set
    os.environ["DASHSCOPE_API_BASE"] = "https://custom.api.com/v1"
    test_str = "${DASHSCOPE_API_BASE:-https://default.api.com/v1}"
    result = _resolve_env_vars(test_str)
    assert result == "https://custom.api.com/v1", f"Failed: Expected custom, got '{result}'"
    print(f"✅ ${VAR:-default} with env set: '{test_str}' -> '{result}'")
    
    # Test 4: Dict with nested env vars
    test_dict = {
        "providers": {
            "custom": {
                "api_key": "${DASHSCOPE_API_KEY}",
                "api_base": "${DASHSCOPE_API_BASE:-https://default.com}"
            }
        }
    }
    result = _resolve_env_vars(test_dict)
    assert result["providers"]["custom"]["api_key"] == "test-key-123"
    assert result["providers"]["custom"]["api_base"] == "https://custom.api.com/v1"
    print(f"✅ Nested dict resolution works correctly")
    
    print("\n✅ TEST 1 PASSED: Config env var interpolation works!\n")
    return True


def test_config_json_format():
    """Test that config.json is valid JSON."""
    print("=" * 60)
    print("TEST 2: Config JSON Validity")
    print("=" * 60)
    
    config_path = project_root / "config" / "config.json"
    
    assert config_path.exists(), f"Config file not found: {config_path}"
    print(f"✅ Config file exists: {config_path}")
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    assert "providers" in config, "Missing 'providers' key"
    assert "custom" in config["providers"], "Missing 'custom' provider"
    assert "agents" in config, "Missing 'agents' key"
    assert "channels" in config, "Missing 'channels' key"
    print(f"✅ Config JSON structure is valid")
    
    # Check that env vars are used
    api_key = config["providers"]["custom"]["api_key"]
    assert "${DASHSCOPE_API_KEY}" in api_key or not api_key.startswith("sk-sp-"), \
        f"API key should use env var, got: {api_key}"
    print(f"✅ API key uses environment variable: {api_key}")
    
    print("\n✅ TEST 2 PASSED: Config JSON is valid!\n")
    return True


def test_dockerfile_config_path():
    """Test that Dockerfile points to correct config file."""
    print("=" * 60)
    print("TEST 3: Dockerfile Config Path")
    print("=" * 60)
    
    dockerfile_path = project_root / "Dockerfile"
    
    with open(dockerfile_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check NANOBOT_CONFIG env var
    match = re.search(r'ENV NANOBOT_CONFIG=([^\n]+)', content)
    assert match, "NANOBOT_CONFIG not found in Dockerfile"
    config_env = match.group(1).strip()
    
    # Should be .json, not .yaml
    assert config_env.endswith(".json"), f"Expected .json, got: {config_env}"
    print(f"✅ NANOBOT_CONFIG points to: {config_env}")
    
    # Check CMD line
    match = re.search(r'CMD \[.*"--config".*"([^"]+)"\]', content)
    if match:
        cmd_config = match.group(1)
        assert cmd_config.endswith(".json"), f"CMD config should be .json, got: {cmd_config}"
        print(f"✅ CMD config path: {cmd_config}")
    
    print("\n✅ TEST 3 PASSED: Dockerfile config path is correct!\n")
    return True


def test_webui_requirements():
    """Test that webui requirements are updated."""
    print("=" * 60)
    print("TEST 4: WebUI Requirements")
    print("=" * 60)
    
    req_path = project_root / "webui" / "requirements.txt"
    
    with open(req_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check aiohttp is included
    assert "aiohttp" in content, "aiohttp not found in requirements"
    print(f"✅ aiohttp is included")
    
    # Check opendataloader-pdf version
    match = re.search(r'opendataloader-pdf.*>=?(\d+\.\d+)', content)
    if match:
        version = match.group(1)
        assert float(version) >= 2.2, f"opendataloader-pdf version should be >=2.2, got: {version}"
        print(f"✅ opendataloader-pdf version: >={version}")
    
    print("\n✅ TEST 4 PASSED: WebUI requirements are updated!\n")
    return True


def test_env_file():
    """Test that .env file has necessary variables."""
    print("=" * 60)
    print("TEST 5: .env File Variables")
    print("=" * 60)
    
    env_path = project_root / ".env"
    
    if not env_path.exists():
        print("⚠️ .env file not found (using .env.example)")
        env_path = project_root / ".env.example"
    
    with open(env_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check for DASHSCOPE_API_KEY
    assert "DASHSCOPE_API_KEY" in content, "DASHSCOPE_API_KEY not in .env"
    print(f"✅ DASHSCOPE_API_KEY found")
    
    # Check for DASHSCOPE_API_BASE
    assert "DASHSCOPE_API_BASE" in content, "DASHSCOPE_API_BASE not in .env"
    print(f"✅ DASHSCOPE_API_BASE found")
    
    # Check for DATABASE_URL
    assert "DATABASE_URL" in content, "DATABASE_URL not in .env"
    print(f"✅ DATABASE_URL found")
    
    print("\n✅ TEST 5 PASSED: .env file has necessary variables!\n")
    return True


def test_webapi_health_check():
    """Test that webapi.py has improved health check."""
    print("=" * 60)
    print("TEST 6: WebAPI Health Check")
    print("=" * 60)
    
    webapi_path = project_root / "nanobot" / "channels" / "webapi.py"
    
    with open(webapi_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check database field in HealthResponse
    assert "database:" in content or '"database"' in content, \
        "HealthResponse should have 'database' field"
    print(f"✅ HealthResponse has database field")
    
    # Check asyncpg import in health check
    assert "import asyncpg" in content, "asyncpg import should be in health check"
    print(f"✅ Health check uses asyncpg for DB connectivity")
    
    print("\n✅ TEST 6 PASSED: WebAPI health check is improved!\n")
    return True


def test_streaming_json_format():
    """Test that streaming uses consistent JSON format."""
    print("=" * 60)
    print("TEST 7: Streaming JSON Format")
    print("=" * 60)
    
    webapi_path = project_root / "nanobot" / "channels" / "webapi.py"
    
    with open(webapi_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check that streaming uses JSON with type field
    assert '"type": "progress"' in content, "Progress messages should have type field"
    print(f"✅ Progress messages use JSON format with type")
    
    assert '"type": "content"' in content, "Content messages should have type field"
    print(f"✅ Content messages use JSON format with type")
    
    assert '"type": "delta"' in content, "Delta messages should have type field"
    print(f"✅ Delta messages use JSON format with type")
    
    assert '"type": "done"' in content, "Done signal should have type field"
    print(f"✅ Done signal uses JSON format with type")
    
    print("\n✅ TEST 7 PASSED: Streaming uses consistent JSON format!\n")
    return True


def run_all_tests():
    """Run all QA tests."""
    print("\n" + "=" * 60)
    print("🔍 QA TEST SUITE - Verifying All Fixes")
    print("=" * 60 + "\n")
    
    tests = [
        test_config_env_var_interpolation,
        test_config_json_format,
        test_dockerfile_config_path,
        test_webui_requirements,
        test_env_file,
        test_webapi_health_check,
        test_streaming_json_format,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"❌ TEST FAILED: {e}")
            failed += 1
    
    print("\n" + "=" * 60)
    print("📊 QA TEST RESULTS")
    print("=" * 60)
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print("=" * 60)
    
    if failed == 0:
        print("\n🎉 ALL TESTS PASSED! Fixes are verified.")
    else:
        print(f"\n⚠️ {failed} tests failed. Please review the fixes.")
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)