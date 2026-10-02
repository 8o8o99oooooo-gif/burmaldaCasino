from aiogram.types import WebAppInfo

# Добавь эту кнопку в главное меню
def main_menu_kb(balance: int):
    builder = InlineKeyboardBuilder()
    builder.button(text="🎮 Играть", callback_data="menu_games")
    builder.button(text="🎁 Ежедневный бонус", callback_data="menu_bonus")
    # Добавляем кнопку Web App
    builder.button(
        text="🌐 Казино (Web App)",
        web_app=WebAppInfo(url="https://твой-сайт.com/index.html")  # Замени на свой URL
    )
    builder.adjust(1)
    return builder.as_markup()
