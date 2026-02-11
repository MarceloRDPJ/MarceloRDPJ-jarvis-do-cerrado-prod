def _build_unknown_device_markup(event):
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    ip = event.payload.get('ip')
    mac = event.payload.get('mac')

    # Callback data must be short (64 bytes limit)
    # net_reg_{ip}_{mac} might be too long.
    # IP max 15, MAC 17. 8 + 15 + 17 = 40. OK.

    keyboard = [
        [
            InlineKeyboardButton("📝 Cadastrar", callback_data=f"net_reg_{ip}_{mac}"),
            InlineKeyboardButton("🚫 Bloquear", callback_data=f"net_block_{ip}")
        ],
        [
            InlineKeyboardButton("👁️ Ignorar", callback_data="net_ignore")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)
