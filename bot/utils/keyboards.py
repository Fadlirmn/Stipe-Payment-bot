"""
utils/keyboards.py — Inline keyboard builder helpers
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_keyboard(role: str) -> InlineKeyboardMarkup:
    """Menu utama — disesuaikan dengan role."""
    base = [
        [
            InlineKeyboardButton("📋 Task Hari Ini", callback_data="menu:task"),
            InlineKeyboardButton("📊 Progress Saya", callback_data="menu:progress"),
        ],
        [
            InlineKeyboardButton("🔗 Verif URL Hari Ini", callback_data="menu:verif"),
            InlineKeyboardButton("📖 History", callback_data="menu:history"),
        ],
    ]

    if role in ("admin", "dev"):
        base.append([
            InlineKeyboardButton("⚙️ Config Task", callback_data="menu:config_task"),
            InlineKeyboardButton("👥 Kelola User", callback_data="menu:users"),
        ])
        base.append([
            InlineKeyboardButton("📈 Report", callback_data="menu:report"),
            InlineKeyboardButton("🔔 Set Reminder", callback_data="menu:reminder"),
        ])
        base.append([
            InlineKeyboardButton("🌐 Dashboard", callback_data="menu:dashboard"),
            InlineKeyboardButton("📥 Sync Sheet", callback_data="menu:sync_sheet"),
        ])

    if role == "dev":
        base.append([
            InlineKeyboardButton("🔧 Dev Tools", callback_data="menu:devtools"),
        ])

    base.append([InlineKeyboardButton("ℹ️ Bantuan", callback_data="menu:help")])
    return InlineKeyboardMarkup(base)


def task_list_keyboard(tasks: list[dict]) -> InlineKeyboardMarkup:
    """Keyboard pilihan task dari daftar task aktif."""
    buttons = [
        [InlineKeyboardButton(
            f"📌 {t['task_id']} — {t['title'][:30]}",
            callback_data=f"task:select:{t['task_id']}",
        )]
        for t in tasks
    ]
    buttons.append([InlineKeyboardButton("🔙 Menu Utama", callback_data="menu:main")])
    return InlineKeyboardMarkup(buttons)


def url_action_keyboard(sheet_url_id: int) -> InlineKeyboardMarkup:
    """Tombol aksi per URL yang siap diverifikasi."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Verifikasi Sekarang", callback_data=f"url:verify:{sheet_url_id}"),
            InlineKeyboardButton("⏭️ Skip", callback_data=f"url:skip:{sheet_url_id}"),
        ],
        [InlineKeyboardButton("🔙 Kembali", callback_data="menu:verif")],
    ])


def confirm_keyboard(confirm_data: str, cancel_data: str = "menu:main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Ya, Lanjutkan", callback_data=confirm_data),
            InlineKeyboardButton("❌ Batal", callback_data=cancel_data),
        ]
    ])


def back_keyboard(callback: str = "menu:main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Kembali", callback_data=callback)]
    ])


def pagination_keyboard(
    current: int, total_pages: int, prefix: str
) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    if current > 1:
        row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"{prefix}:page:{current-1}"))
    row.append(InlineKeyboardButton(f"{current}/{total_pages}", callback_data="noop"))
    if current < total_pages:
        row.append(InlineKeyboardButton("Next ➡️", callback_data=f"{prefix}:page:{current+1}"))
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("🔙 Kembali", callback_data="menu:main")])
    return InlineKeyboardMarkup(buttons)
