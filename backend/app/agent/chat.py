"""自由对话助手:给 Unity 端的聊天框用。

与 ``planner`` 的强制工具调用不同,这里就是普通的多轮对话——回答关于流水线、
参数选择、报错排查的问题。有 ``ANTHROPIC_API_KEY`` 时走 Claude,否则规则版兜底。
"""
from __future__ import annotations

import logging
from typing import Any

from ..config import Settings
from ..config import settings as default_settings

log = logging.getLogger(__name__)

CHAT_SYSTEM_PROMPT = (
    "你是 3DGS-Agent 项目的助理。用简体中文简洁回答(每次回复控制在 5 句以内)。"
    "你能解释:流水线(预处理 → COLMAP → 训练 3DGS → 转换 → 打包)、"
    "参数(preset 在 preview/balanced/high 之间选;train.backend 在 vanilla/mip/2dgs/relight 之间选)、"
    "报错排查、以及扩展(Mip-Splatting/2DGS/Relightable/VR)。"
    "不要凭空假设用户已经做了什么。涉及具体路径或命令时给可执行的形式。"
)


def _mock_reply(last_user: str) -> str:
    t = (last_user or "").lower()
    if any(k in t for k in ["快", "preview", "预览", "迅速"]):
        return "选 `preset=preview`(约 7k 迭代,几分钟出图),先看效果再用 `balanced` 或 `high` 重训。"
    if any(k in t for k in ["抗锯齿", "mip", "闪烁", "锯齿", "alias"]):
        return "把 `train.backend` 设为 `mip`(Mip-Splatting),抗锯齿、远处稳定;输出仍是 `.ply`,aras-p 导入器可直接读。"
    if any(k in t for k in ["重光照", "relight", "光照"]):
        return "用 `backend=relight`(Relightable3DGaussian),改训练 + 渲染路径,工作量最大;轻量替代:Unity 端做近似 BRDF。"
    if any(k in t for k in ["2dgs", "网格", "mesh", "表面"]):
        return "想要干净表面/网格用 `backend=2dgs`,从 disk 高斯 TSDF 出网格,可作普通 Unity Mesh 导入。"
    if any(k in t for k in ["unity", "导入", ".ply", "ply"]):
        return "Unity 6 工程装 aras-p 插件;把 `data/jobs/<id>/result/model.ply` 拖进工程,会生成 GaussianSplatAsset;或用 `tools/unity_3dgs_importer` 一键导入。"
    if any(k in t for k in ["gpu", "cuda", "显存", "nvml"]):
        return "本机 NVML 版本不匹配,重启或重装匹配驱动可恢复;真训练前先 `nvidia-smi` 能跑通。"
    if any(k in t for k in ["colmap", "位姿", "sfm"]):
        return "`apt install colmap` 装好后,真实模式会跑 feature_extractor → matcher → mapper → image_undistorter;无 GPU 加 `--SiftExtraction.use_gpu 0`。"
    if any(k in t for k in ["失败", "错误", "报错", "error", "fail"]):
        return "看 `data/jobs/<id>/logs/<stage>.log` 与最后一次 SSE 事件;COLMAP 失败常见原因是图片太少/重叠太低,加图重试。"
    if any(k in t for k in ["你好", "hi", "hello"]):
        return "你好!我是 3DGS-Agent 助理。可以问我:配置选择、流水线阶段、报错、Unity 导入。"
    return "我会:解释流水线 / 选参数 / 排查报错 / 解答 Unity 导入。说具体点会更好,例如:'重建这把椅子,要高质量+远处不闪烁'。"


class MockChat:
    name = "mock"

    def reply(self, messages: list[dict[str, Any]]) -> str:
        last_user = next(
            (m["content"] for m in reversed(messages) if m.get("role") == "user" and m.get("content")),
            "",
        )
        return _mock_reply(last_user)


class ClaudeChat:
    name = "claude"

    def __init__(self, settings: Settings):
        self.settings = settings
        self._fallback = MockChat()
        from anthropic import Anthropic  # 延迟导入

        self._client = Anthropic(api_key=settings.anthropic_api_key)

    def reply(self, messages: list[dict[str, Any]]) -> str:
        try:
            msg = self._client.messages.create(
                model=self.settings.agent_model,
                max_tokens=512,
                system=[{"type": "text", "text": CHAT_SYSTEM_PROMPT,
                         "cache_control": {"type": "ephemeral"}}],
                messages=messages,
            )
            for block in msg.content:
                if getattr(block, "type", None) == "text":
                    return block.text.strip()
        except Exception as exc:  # noqa: BLE001
            log.warning("chat: Claude call failed (%s); falling back to mock", exc)
        return self._fallback.reply(messages)


def get_chat(settings: Settings | None = None):
    settings = settings or default_settings
    if settings.llm_enabled:
        try:
            return ClaudeChat(settings)
        except Exception as exc:  # noqa: BLE001
            log.warning("chat: cannot init Claude (%s); using mock", exc)
    return MockChat()
