"""14 天前的 NotebookLM notebook 自動刪除。

用法:
  python cleanup.py            # 實際刪除
  python cleanup.py --dry-run  # 只列出會刪掉哪些,不動手

建議掛 Windows Task Scheduler 或 cron 每天跑一次。
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone

import config
from notebook_service import NotebookLMService


async def cleanup(dry_run: bool = False) -> None:
    service = NotebookLMService()
    cutoff = datetime.now(timezone.utc) - timedelta(days=config.NOTEBOOK_RETENTION_DAYS)

    notebooks = await service.list_notebooks()
    print(f"共 {len(notebooks)} 個 notebook,保留 {config.NOTEBOOK_RETENTION_DAYS} 天")

    to_delete = []
    for nb in notebooks:
        # nb 物件應該有 created_at / modified_at(notebooklm-py 規格)
        created = getattr(nb, "created_at", None) or getattr(nb, "modified_at", None)
        if created and created < cutoff:
            to_delete.append(nb)

    print(f"待刪除: {len(to_delete)} 個")
    for nb in to_delete:
        name = getattr(nb, "title", None) or getattr(nb, "name", "?")
        created = getattr(nb, "created_at", "?")
        print(f"  - [{created}] {name} ({nb.id})")
        if not dry_run:
            try:
                await service.delete_notebook(nb.id)
                print(f"    ✓ 已刪除")
            except Exception as e:  # noqa: BLE001
                print(f"    ✗ 失敗: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="只列出,不實際刪除")
    args = parser.parse_args()
    asyncio.run(cleanup(dry_run=args.dry_run))
