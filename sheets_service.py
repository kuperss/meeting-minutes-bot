"""Google Sheets 服務:複製範本分頁 → 填入欄位。

用 gspread + service account。使用前必須把 Sheet 分享給 service account email
(就是 service_account.json 裡 "client_email" 那個地址)。
"""
from __future__ import annotations

from datetime import date

import gspread
from google.oauth2.service_account import Credentials

import config


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


class SheetsService:
    def __init__(self):
        creds = Credentials.from_service_account_file(
            config.GOOGLE_SERVICE_ACCOUNT_JSON, scopes=SCOPES
        )
        self.gc = gspread.authorize(creds)
        self.spreadsheet = self.gc.open_by_key(config.SPREADSHEET_ID)

    def create_meeting_tab(
        self,
        meeting_date: date,
        recorder: str,
        main_content: list[str],
        followup_items: list[str],
    ) -> str:
        """從範本複製新分頁,填入所有欄位。回傳新分頁名。"""
        # 1. 取範本 worksheet
        template = self.spreadsheet.worksheet(config.TEMPLATE_SHEET_NAME)

        # 2. 新分頁名 (M.D 格式,例: "4.25")
        tab_date_str = f"{meeting_date.month}.{meeting_date.day}"
        new_tab_name = config.SHEET_TAB_NAME_FORMAT.format(date=tab_date_str)
        new_tab_name = self._ensure_unique_name(new_tab_name)
        # 寫入 G2 用完整日期 YYYY/MM/DD
        date_str = meeting_date.strftime("%Y/%m/%d")

        # 3. 複製範本
        new_sheet = template.duplicate(new_sheet_name=new_tab_name)

        # 4. 填欄位
        layout = config.LAYOUT
        updates = [
            {"range": layout.date_cell, "values": [[date_str]]},
            {"range": layout.recorder_cell, "values": [[recorder]]},
            {
                "range": layout.status_cell,
                "values": [["待追蹤" if followup_items else "無"]],
            },
        ]

        # 主要內容 (最多 N 條,超過截斷;空白列保留模板原本的 "1.", "2."...)
        max_main = layout.main_content_end_row - layout.main_content_start_row + 1
        for i in range(max_main):
            row = layout.main_content_start_row + i
            content = main_content[i] if i < len(main_content) else ""
            if content:
                value = f"{i+1}. {content}" if layout.main_content_numbered else content
            else:
                # 空白列保留範本原本的編號 "1.", "2."...
                value = f"{i+1}." if layout.main_content_numbered else ""
            updates.append(
                {
                    "range": f"{layout.main_content_col}{row}",
                    "values": [[value]],
                }
            )

        # 需後續追蹤事項
        followup_truncated = followup_items[: layout.followup_max_rows]
        for i, item in enumerate(followup_truncated):
            row = layout.followup_start_row + i
            updates.append(
                {
                    "range": f"{layout.followup_col}{row}",
                    "values": [[item]],
                }
            )

        # 批次寫入 (減少 API 呼叫)
        new_sheet.batch_update(updates, value_input_option="USER_ENTERED")

        return new_tab_name

    def _ensure_unique_name(self, name: str) -> str:
        """若分頁名重複,加後綴 (例: 2025/10/08 → 2025/10/08 (2))。"""
        existing = {ws.title for ws in self.spreadsheet.worksheets()}
        if name not in existing:
            return name
        n = 2
        while f"{name} ({n})" in existing:
            n += 1
        return f"{name} ({n})"
