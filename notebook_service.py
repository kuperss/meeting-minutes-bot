"""notebooklm-py 包裝:封裝常用流程,便於 pipeline 呼叫。"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

from notebooklm import NotebookLMClient
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

import config
from logging_setup import log
from prompts import MEETING_MINUTES_PROMPT


# 哪些例外要重試 (網路/暫時性錯誤)
RETRYABLE_EXC = (asyncio.TimeoutError, ConnectionError, OSError)


class NotebookLMService:
    def __init__(self, storage_path: str | None = None):
        self.storage_path = storage_path or config.NOTEBOOKLM_STORAGE

    async def _client(self) -> NotebookLMClient:
        return await NotebookLMClient.from_storage(self.storage_path)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=4, max=30),
        retry=retry_if_exception_type(RETRYABLE_EXC),
        before_sleep=before_sleep_log(log, 30),  # logging.WARNING = 30
        reraise=True,
    )
    async def process_audio(self, audio_path: Path, notebook_name: str) -> dict:
        """建 notebook → 上傳音檔 → 取逐字稿 → 問結構化摘要。

        回傳 {"notebook_id", "transcript", "minutes"}
        """
        log.info("建立 notebook: %s", notebook_name)

        async with await self._client() as client:
            nb = await client.notebooks.create(notebook_name)
            log.info("notebook 已建立,id=%s", nb.id)

            log.info("上傳音檔 %s (%.1f KB)…", audio_path.name, audio_path.stat().st_size / 1024)
            source = await client.sources.add_file(nb.id, str(audio_path), wait=True)
            log.info("音檔處理完成,source_id=%s", source.id)

            transcript = ""
            try:
                fulltext = await client.sources.get_fulltext(nb.id, source.id)
                # SourceFulltext 是 dataclass,真正的字串在 .content
                transcript = getattr(fulltext, "content", "") or ""
                log.info("逐字稿取得,%d 字", len(transcript))
            except Exception as e:  # noqa: BLE001
                log.warning("取得逐字稿失敗 (不致命): %s", e)

            log.info("請 NotebookLM 產生結構化摘要…")
            answer = await client.chat.ask(nb.id, MEETING_MINUTES_PROMPT)
            minutes = self._parse_minutes(answer.answer)
            log.info(
                "摘要 parsed,主要內容 %d 條,追蹤事項 %d 條",
                len(minutes.get("main_content", [])),
                len(minutes.get("followup_items", [])),
            )

            return {
                "notebook_id": nb.id,
                "transcript": transcript,
                "minutes": minutes,
            }

    @staticmethod
    def _parse_minutes(raw: str) -> dict:
        """從 LLM 回覆中抓出 JSON(容錯 ```json``` 圍欄 / 前後綴文字)。"""
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise ValueError(f"無法從 NotebookLM 回覆抓出 JSON:\n{raw[:500]}")
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError as e:
            raise ValueError(f"NotebookLM 回覆的 JSON 格式錯誤: {e}\n原文: {raw[:500]}") from e

        # 欄位預設值
        parsed.setdefault("main_content", [])
        parsed.setdefault("followup_items", [])
        # 型別檢查
        if not isinstance(parsed["main_content"], list) or not isinstance(
            parsed["followup_items"], list
        ):
            raise ValueError("JSON 欄位型別錯誤:main_content / followup_items 必須是陣列")
        return parsed

    async def list_notebooks(self) -> list:
        async with await self._client() as client:
            return await client.notebooks.list()

    async def delete_notebook(self, notebook_id: str) -> None:
        async with await self._client() as client:
            await client.notebooks.delete(notebook_id)
