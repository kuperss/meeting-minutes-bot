"""核心流程:audio → NotebookLM → Google Sheet。"""
from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path
from typing import Callable

import config
from logging_setup import log
from notebook_service import NotebookLMService
from sheets_service import SheetsService


async def process_meeting(
    audio_path: Path,
    recorder: str,
    meeting_date: date | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict:
    """執行完整流程,回傳結果摘要。

    progress callback 推進度給前端看。
    """
    meeting_date = meeting_date or date.today()
    p = progress or (lambda msg: None)

    log.info(
        "開始處理: audio=%s recorder=%s date=%s", audio_path.name, recorder, meeting_date
    )

    p("上傳音檔到 NotebookLM 並等待解析…")
    notebook_name = config.NOTEBOOK_NAME_FORMAT.format(
        date=meeting_date.strftime("%Y%m%d")
    )

    nb_service = NotebookLMService()
    result = await nb_service.process_audio(audio_path, notebook_name)

    minutes = result["minutes"]
    p(
        f"摘要產出: 主要內容 {len(minutes.get('main_content', []))} 條, "
        f"追蹤事項 {len(minutes.get('followup_items', []))} 條"
    )

    p("寫入 Google Sheet…")
    sheets = SheetsService()
    tab_name = await asyncio.to_thread(
        sheets.create_meeting_tab,
        meeting_date,
        recorder,
        minutes.get("main_content", []),
        minutes.get("followup_items", []),
    )

    p(f"完成: 分頁 '{tab_name}' 已建立")

    return {
        "tab_name": tab_name,
        "notebook_id": result["notebook_id"],
        "minutes": minutes,
        "transcript_preview": (result["transcript"] or "")[:500],
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python pipeline.py <audio_file> <recorder>")
        sys.exit(1)

    audio = Path(sys.argv[1])
    recorder = sys.argv[2]

    async def main():
        result = await process_meeting(
            audio, recorder, progress=lambda m: print(f"[進度] {m}")
        )
        print("\n=== 結果 ===")
        print(f"分頁: {result['tab_name']}")
        print(f"Notebook ID: {result['notebook_id']}")
        print(f"摘要: {result['minutes']}")

    asyncio.run(main())
