import os


def _normalize_api_key(value: str) -> str:
    """清理从控制台或 IDE 复制时可能附带的空格和成对引号。"""
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1].strip()
    return value


def resolve_api_key(api_key_or_env: str, provider: str) -> str:
    """兼容环境变量名称和直接填写的 API Key。"""
    key_or_env = _normalize_api_key(api_key_or_env)
    if key_or_env.startswith("sk-"):
        return key_or_env

    api_key = os.getenv(key_or_env)
    if not api_key:
        raise RuntimeError(
            f"未设置{provider} API Key，请配置环境变量 {key_or_env}，"
            "或在配置文件中直接填写 API Key"
        )
    api_key = _normalize_api_key(api_key)
    if not api_key.startswith("sk-"):
        raise RuntimeError(
            f"{provider} API Key 格式不正确：环境变量 {key_or_env} 的值应以 sk- 开头"
        )
    return api_key
