# Tg_bot/keyboards.py
import logging
from typing import Any, Dict, List, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from tg_bot.models import CommunicationThread, Order, OrderStatus, Product, User, UserRole, UserStatus

# Инициализация логгера
logger = logging.getLogger(__name__)

# Префиксы
CB_PREFIX_APPROVE = "approve_"
CB_PREFIX_DECLINE = "decline_"
CB_CLOSE_GENERIC = "close_generic"
CB_PREFIX_SELECT_CATEGORY = "cat_sel_"
CB_SHOW_ALL_PRODUCTS = "cat_sel_all"
CB_GO_TO_MAIN_MENU = "main_menu"
CB_PREFIX_SELECT_PRODUCT = "prod_sel_"
CB_BACK_TO_CATEGORIES = "back_to_cat"
CB_PREFIX_CHANGE_QUANTITY = "prod_qty_"
CB_ADD_TO_CART = "add_to_cart_"
CB_BACK_TO_PRODUCT_LIST = "back_to_prod_list_"
CB_PREFIX_CATEGORY_LIST = "cat_list_"
CB_VIEW_CART = "view_cart"
CB_CHECKOUT = "checkout"
CB_CLEAR_CART = "clear_cart"
CB_USER_MY_ORDERS = "user_my_orders"
CB_USER_START_ORDERING = "user_start_ordering"
CB_PREFIX_USER_ORDER_DETAILS = "user_order_details_"
CB_PREFIX_USER_CONTACT_SUPPORT = "user_contact_support_"
CB_USER_SHOW_MAIN_MENU = "user_show_main_menu"
CB_PREFIX_USER_CANCEL_ORDER = "user_cancel_order_"
CB_USER_ADD_COMMENT_ORDER = "user_add_comment_order_"
CB_USER_EDIT_COMMENT_ORDER = "user_edit_comment_order_"
CB_USER_DELETE_COMMENT_ORDER = "user_delete_comment_order_"
CB_PREFIX_ADMIN = "admin_"
CB_ADMIN_USERS = f"{CB_PREFIX_ADMIN}users"
CB_ADMIN_ORDERS = f"{CB_PREFIX_ADMIN}orders"
CB_ADMIN_STATS = f"{CB_PREFIX_ADMIN}stats"
CB_ADMIN_SETTINGS = f"{CB_PREFIX_ADMIN}settings"
CB_ADMIN_BACK_TO_MAIN = f"{CB_PREFIX_ADMIN}main"
CB_ADMIN_ORDERS_MENU = f"{CB_PREFIX_ADMIN}orders_menu"
CB_PREFIX_ORDERS_BY_STATUS = f"{CB_PREFIX_ADMIN}orders_status_"
CB_PREFIX_ORDER_DETAILS = f"{CB_PREFIX_ADMIN}order_details_"
CB_PREFIX_ORDER_ACTION = f"{CB_PREFIX_ADMIN}order_action_"
CB_ADMIN_COMMUNICATION_CENTER = f"{CB_PREFIX_ADMIN}comms_center"
CB_ADMIN_SYNC_PRODUCTS = f"{CB_PREFIX_ADMIN}sync_products"
CB_PREFIX_THREAD_DETAILS = f"{CB_PREFIX_ADMIN}thread_details_"
CB_PREFIX_THREAD_ACTION = f"{CB_PREFIX_ADMIN}thread_action_"
CB_ADMIN_BACK_TO_THREADS_LIST = f"{CB_PREFIX_ADMIN}comms_back_list"
CB_PREFIX_USERS_BY_STATUS = f"{CB_PREFIX_ADMIN}users_status_"
CB_PREFIX_USER_DETAILS = f"{CB_PREFIX_ADMIN}user_details_"
CB_ADMIN_BACK_TO_USERS = f"{CB_PREFIX_ADMIN}users_main"
CB_PREFIX_USER_ACTION = f"{CB_PREFIX_ADMIN}user_action_"
CB_PREFIX_USERS_BY_ROLE = f"{CB_PREFIX_ADMIN}users_role_"
CB_ADMIN_TOGGLE_AUTO_APPROVE = f"{CB_PREFIX_ADMIN}toggle_auto_approve"
CB_CANCEL_NO_REASON = "cancel_no_reason"
CB_DONT_CANCEL = "dont_cancel"
CB_DELIVERY_TYPE_YANDEX = "delivery_yandex"
CB_SEARCH_SEMANTIC = "search_semantic_start"
CB_BREW_GUIDE = "p_brew_"
CB_AI_GIFT_RETRY = "gift_ai_retry"
CB_PICKUP_POINT_SEL = "p_pt_sel_"
CB_GUEST_CATALOG = "guest_catalog"
CB_STAFF_PANEL = f"{CB_PREFIX_ADMIN}panel_start"
CB_STAFF_MAKE_ORDER = "staff_make_order"
CB_STAFF_SHOW_PROFILE = "staff_show_profile"
CB_ADMIN_BACK_TO_STAFF_MENU = "admin_back_to_staff_menu"
CB_OPEN_SORT_MENU = "open_sort_menu"
CB_PREFIX_SET_SORT = "set_sort_"
SORT_PRICE_ASC = "price_asc"   # Дешевые
SORT_PRICE_DESC = "price_desc" # Дорогие
SORT_NAME_ASC = "name_asc"     # А-Я
SORT_NAME_DESC = "name_desc"   # Я-А
SORT_SCA_DESC = "sca_desc"     # Высокая оценка (лучшие)
SORT_SCA_ASC = "sca_asc"       # Низкая оценка
CB_TOGGLE_VIEW = "toggle_view"
CB_GALLERY_PREV = "gal_prev"
CB_GALLERY_NEXT = "gal_next"
CB_GALLERY_ADD = "gal_add"
CB_GALLERY_OPEN_LIST = "gal_open_list"
CB_INFO_MENU = "info_menu"         # Главный вход
CB_PREFIX_INFO_GO = "info_go_"     # Переход в папку
CB_PREFIX_INFO_ADD = "info_add_"   # Создать подраздел
CB_PREFIX_INFO_EDIT = "info_edit_" # Редактировать контент
CB_PREFIX_INFO_DEL = "info_del_"   # Удалить страницу
CB_INFO_BACK = "info_back_"        # Назад к родителю
CB_EDIT_TITLE = "cms_edit_title"
CB_EDIT_CONTENT = "cms_edit_content"
CB_EDIT_ORDER = "cms_edit_order"
CB_CMS_MODE_TOGGLE = "cms_toggle_mode"  # Вкл/выкл режим правки
CB_CMS_ITEM_OPTS = "cms_item_"          # Открыть настройки пункта
CB_CMS_MOVE_UP = "cms_move_up_"
CB_CMS_MOVE_DOWN = "cms_move_down_"
CB_CMS_RENAME = "cms_rename_"
CB_DELIVERY_TYPE_PICKUP = "delivery_pickup" # ПВЗ (WebApp)
CB_DELIVERY_TYPE_COURIER = "delivery_courier" # Курьер
CB_DELIVERY_BACK = "delivery_back"
CB_DELIVERY_TYPE_SELF = "delivery_self"
CB_PREFIX_THREAD_PAGE = "thread_page_"
CB_USER_VIEW_THREAD = "user_view_thread_"
CB_EDIT_CART = "cart_edit_mode"
CB_BACK_TO_CART_SUMMARY = "cart_back_summary"
CB_PREFIX_CART_INC = "c_inc_"
CB_PREFIX_CART_DEC = "c_dec_"
CB_PREFIX_CART_DEL = "c_del_"
CB_ADMIN_SETUP_YANDEX = f"{CB_PREFIX_ADMIN}setup_yandex"
CB_ADMIN_SAVE_YANDEX = f"{CB_PREFIX_ADMIN}save_yandex_"
CB_SAVE_DELIVERY_ADDRESS = "save_dlv_addr"  # Кнопка сохранения
CB_USE_DEFAULT_ADDRESS = "use_def_addr_"    # Кнопка "Использовать по умолчанию"
CB_MANAGE_ADDRESSES = "manage_addresses"    # Меню адресов в профиле
CB_PREFIX_ADDR_DEL = "addr_del_"            # Удаление адреса
CB_PREFIX_ADDR_DEF = "addr_def_"            # Сделать дефолтным
CB_USER_SETTINGS = "user_settings"
CB_USER_ADDRESSES = "user_my_addresses"
CB_PREFIX_ADDR_VIEW = "addr_view_"
CB_BACK_TO_SETTINGS = "back_to_settings"
CB_BACK_TO_ADDR_LIST = "back_to_addr_list"
CB_PREFIX_ADDR_RENAME = "addr_ren_"
CB_FAVORITES_MENU = "user_favorites_menu"
CB_PREFIX_TOGGLE_FAV = "fav_toggle_"   # Переключение в карточке товара
CB_PREFIX_RM_FAV = "fav_remove_"       # Удаление из списка избранного
CB_PREFIX_NOTIFY_FAV = "fav_notify_"   # Подписка на уведомление
CB_FAV_OPEN_PRODUCT = "fav_open_"      # Открыть товар из избранного
CB_GIFT_FOR_ME = "gift_no"             # Константы для выбора подарка
CB_GIFT_AS_PRESENT = "gift_yes"        # Константы для выбора подарка
CB_GIFT_SKIP = "gift_skip"
CB_GIFT_BACK = "gift_back" # Возврат к выбору "Себе/Подарок"
CB_FAV_ADD_CART = "fav_to_cart_"
CB_FAV_UNDO_RM = "fav_undo_"
CB_READ_FULL_DESC = "read_full_desc_"
CB_FAV_INC_CART = "f_inc_"  # +1
CB_FAV_DEC_CART = "f_dec_"  # -1
CB_CART_UNDO_RM = "c_undo_"
CB_PREFIX_PROD_IMG = "p_img_"
CB_PREFIX_IMG_GRID = "p_grid_"
CB_PREFIX_QTY_GRID = "p_q_grid_"  # Вызов сетки количества
CB_PREFIX_SET_QTY = "p_set_q_"    # Установка конкретного числа
CB_PRODUCT_CLEAR = "p_clr_"       # Очистка товара из корзины
CB_PREFIX_FAV_QTY_GRID = "f_q_grid_" # Префиксы для сетки количества именно в Избранном
CB_PREFIX_FAV_SET_QTY = "f_set_q_"
CB_FAV_CART_CLEAR = "f_c_clr_"
CB_PREFIX_CART_QTY_GRID = "c_q_grid_"
CB_PREFIX_CART_SET_QTY = "c_set_q_"
CB_ORDER_RESTORE = "ord_res_" # Восстановление отмененного заказа
CB_REPEAT_ORDER = "user_repeat_ord_"
CB_SEARCH_PRODUCTS = "user_search_start"
CB_ADMIN_COURIER_MGMT = "adm_courier_main"
CB_ADMIN_COURIER_TOGGLE = "adm_courier_tog"
CB_ADMIN_COURIER_ADD_CITY = "adm_courier_add"
CB_ADMIN_COURIER_DEL_CITY = "adm_courier_del_"
CB_DELIVERY_COURIER_CITY = "dlv_cour_city_"
CB_USER_RATE_ORDER_START = "u_rate_start_"
CB_USER_SET_RATING = "u_set_rat_"
CB_USER_LOGOUT_MENU = "user_logout_menu"
CB_USER_LOGOUT_ONLY = "user_logout_confirm"
CB_USER_DELETE_DATA = "user_delete_data_confirm"
CB_RESTART_BOT = "restart_bot"
CB_AI_CHAT_START = "ai_chat_start"
CB_AI_CHAT_HISTORY = "ai_chat_history"
CB_AI_HIST_PAGE = "ai_hp_"
CB_ROUTER_ASK_AI = "rt_ask_ai"
CB_ROUTER_SUPPORT = "rt_support"
CB_SUPPORT_CONSULTATION = "sup_cons" # Общая консультация
CB_ROUTER_ORDER_LIST = "rt_order_list"
CB_AI_GIFT_HELP = "gift_ai_help"
CB_PREFIX_AI_GIFT_SELECT = "g_ai_s_"
CB_RECIPE_VIEW_SAVED = "rec_v_sv_" # Просмотр сохраненного текста
CB_RECIPE_SAVE = "rec_save_"
CB_RECIPE_BACK = "rec_back_"
CB_FAV_RECIPES_LIST = "fav_rec_list"
CB_RECIPE_DELETE = "rec_del_"
CB_BREW_METHOD_SELECT = "p_br_meth_"
CB_ADMIN_PICKUP_MGMT = "adm_p_main"
CB_ADMIN_PICKUP_ADD = "adm_p_add"
CB_PREFIX_ADMIN_PICKUP_VIEW = "adm_p_view_"    # Для просмотра настроек точки
CB_PREFIX_ADMIN_PICKUP_TOGGLE = "adm_p_tog_"  # Для Вкл/Выкл
CB_ADMIN_PICKUP_EDIT = "adm_p_edit_"           # Для редактирования полей
CB_PREFIX_ADMIN_PICKUP_DEL = "adm_p_del_"      # Для удаления
CB_ADMIN_PICKUP_BACK_TO_NAME = "p_back_name"
CB_ADMIN_PICKUP_BACK_TO_ADDR = "p_back_addr"
CB_ADMIN_PICKUP_BACK_TO_SCHED = "p_back_sched"
CB_START_REGISTRATION = "start_reg_wizard"
CB_FAV_PRODUCTS_LIST = "fav_prod_list"
CB_ADMIN_LOGO_MGMT = "adm_logo_main"
CB_ADMIN_LOGO_SET = "adm_logo_set"
CB_ADMIN_LOGO_DEL = "adm_logo_del"
CB_ADMIN_WELCOME_TEXT_EDIT = "adm_w_txt_ed"
CB_ADMIN_PROXY_MGMT = f"{CB_PREFIX_ADMIN}proxy_main"
CB_ADMIN_PROXY_SET = f"{CB_PREFIX_ADMIN}proxy_set"
CB_ADMIN_PROXY_DEL = f"{CB_PREFIX_ADMIN}proxy_del"
CB_ADMIN_PROXY_TOGGLE = f"{CB_PREFIX_ADMIN}proxy_tog"

# Иконки для категорий (используем реальные unicode символы)
CATEGORY_ICONS = {
    "Кофе": "☕",
    "Чай": "🍵",
    "Мерч": "🧢",
    "Эспрессо": "☕",
    "Фильтр": "⬛",   # Черный квадрат для черного кофе
    "Дрипы": "🧧",    # Конвертик похож на дрип-пакет
    "Аксессуары": "⚙️",
    "Зерно": "🫘",
    "Молотый": "🧱"
}

def get_icon(name: str) -> str:
    """Возвращает иконку для категории с пробелом или пустую строку."""
    name_lower = name.lower()

    # 1. точное совпадение
    if name in CATEGORY_ICONS:
        return f"{CATEGORY_ICONS[name]} "

    # 2. частичное совпадение (например, "кофе в зернах" найдет иконку "кофе")
    for key, icon in CATEGORY_ICONS.items():
        if key.lower() in name_lower:
            return f"{icon} "

    return ""


# Клавиатуры для регистрации и админки
def get_contact_keyboard() -> ReplyKeyboardMarkup:
    button = KeyboardButton("Поделиться контактом", request_contact=True)
    return ReplyKeyboardMarkup([[button]], resize_keyboard=True, one_time_keyboard=True)

def get_admin_approval_keyboard(telegram_id: int) -> InlineKeyboardMarkup:
    buttons = [[
        InlineKeyboardButton("✅ Одобрить", callback_data=f"{CB_PREFIX_APPROVE}{telegram_id}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"{CB_PREFIX_DECLINE}{telegram_id}")
    ]]
    return InlineKeyboardMarkup(buttons)

def get_admin_order_keyboard(order_id: int) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton("✅ Выдать заказ", callback_data=f"{CB_PREFIX_ORDER_ACTION}_issue_{order_id}")]]
    return InlineKeyboardMarkup(buttons)


def get_staff_main_keyboard(is_cart_empty: bool = True) -> InlineKeyboardMarkup:
    """Главная Inline-клавиатура для всего персонала."""
    keyboard = [
        [InlineKeyboardButton("🗂 Панель управления", callback_data=CB_STAFF_PANEL)],
        [
            InlineKeyboardButton("📦 Товары", callback_data=CB_STAFF_MAKE_ORDER),
            InlineKeyboardButton("💬 Мой профиль", callback_data=CB_STAFF_SHOW_PROFILE)
        ]
    ]

    # Если корзина не пуста, добавляем кнопку "корзина"
    if not is_cart_empty:
        keyboard.append([InlineKeyboardButton("🛒 Перейти в корзину", callback_data=CB_VIEW_CART)])

    keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data=CB_USER_SHOW_MAIN_MENU)])

    return InlineKeyboardMarkup(keyboard)


def get_category_keyboard(categories: List[str], cart: dict[str, Any], is_staff: bool = False, back_to_main: bool = True, current_category: Optional[str] = None, has_favorites: bool = False, is_guest: bool = False) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру выбора категории.
    Изменено: Избранное и Корзина теперь отображаются в один ряд (плоскость) для экономии места.
    Добавлено: Логика гостевого режима (is_guest).
    """
    logger.info(f"Generating category keyboard. Favs: {has_favorites}, Cart items: {len(cart) if cart else 0}, Guest: {is_guest}")
    keyboard = []

    # 1. поиск товаров (только для авторизованных)
    if not is_guest:
        keyboard.append([InlineKeyboardButton("🔍 Поиск товаров", callback_data=CB_SEARCH_PRODUCTS)])

    row = []
    # 2. кнопки подкатегорий (сетка 2xn)
    for category in categories:
        icon = get_icon(category)
        text = f"{icon}{category}"
        row.append(InlineKeyboardButton(text, callback_data=f"{CB_PREFIX_SELECT_CATEGORY}{category}"))

        if len(row) == 2:
            keyboard.append(row)
            row = []

    # 3. кнопка "все товары"
    all_products_cb = f"{CB_PREFIX_CATEGORY_LIST}{current_category}" if current_category else CB_SHOW_ALL_PRODUCTS
    all_products_btn = InlineKeyboardButton("🗂 Все товары", callback_data=all_products_cb)

    if len(row) == 1:
        row.append(all_products_btn)
        keyboard.append(row)
    else:
        if row:
            keyboard.append(row)
        keyboard.append([all_products_btn])

    # Логика гостя vs пользователя
    if is_guest:
        # В режиме гостя убираем корзину/меню и ставим кнопку регистрации
        keyboard.append([InlineKeyboardButton("📝 Начать регистрацию", callback_data=CB_START_REGISTRATION)])
    else:
        # 4. обычный объединенный ряд: избранное + корзина
        system_row = []
        if has_favorites:
            system_row.append(InlineKeyboardButton("❤️ Избранное", callback_data=CB_FAVORITES_MENU))

        if cart:
            cart_btn_text = "🛒 Корзина" if has_favorites else "🛒 Перейти в корзину"
            system_row.append(InlineKeyboardButton(cart_btn_text, callback_data=CB_VIEW_CART))

        if system_row:
            keyboard.append(system_row)

        # 5. кнопка назад/меню
        if is_staff:
            keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data=CB_STAFF_PANEL)])
        else:
            if back_to_main:
                keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data=CB_GO_TO_MAIN_MENU)])
            else:
                keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data=CB_BACK_TO_CATEGORIES)])

    logger.debug(f"UI Category: Keyboard built with {'GUEST button' if is_guest else 'system buttons'}.")
    return InlineKeyboardMarkup(keyboard)


def get_product_list_keyboard(products: List[Product], category: str, cart: dict[str, Any], highlight_id: Optional[int] = None, is_guest: bool = False) -> InlineKeyboardMarkup:
    """
    Клавиатура списка товаров.
    :param highlight_id: ID товара, который нужно визуально выделить (для навигации из Галереи).
    Добавлено: Логика гостевого режима (is_guest).
    """
    keyboard = []
    for product in products:
        price_str = f"{product.variants[0].price}₽" if product.variants else "???"

        # Маркировка текущего товара
        prefix = "👉 " if product.id == highlight_id else ""
        btn_text = f"{prefix}{product.name} - {price_str}"

        callback_data = f"{CB_PREFIX_SELECT_PRODUCT}{product.id}_{category}"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=callback_data)])

    # Сортировка и назад доступны всем
    keyboard.append([InlineKeyboardButton("⇅ Сортировка / Вид", callback_data=CB_OPEN_SORT_MENU)])
    keyboard.append([InlineKeyboardButton("⬅️ Назад к категориям", callback_data=CB_BACK_TO_CATEGORIES)])

    if is_guest:
        # Гостю — регистрацию
        keyboard.append([InlineKeyboardButton("📝 Начать регистрацию", callback_data=CB_START_REGISTRATION)])
    elif cart:
        # Покупателю — корзину
        keyboard.append([InlineKeyboardButton("🛒 Перейти в корзину", callback_data=CB_VIEW_CART)])

    return InlineKeyboardMarkup(keyboard)


def get_product_view_keyboard(
    product_id: int, category: str, quantity: int, cart: dict[str, Any],
    details_shown: bool = False, is_staff: bool = False, is_favorite: bool = False,
    has_overflow: bool = False, img_index: int = 0, img_total: int = 1, is_guest: bool = False
) -> InlineKeyboardMarkup:
    """
    Ультимативная клавиатура KOJO.
    Навигация 'Избранное' и 'Корзина' объединены в один ряд.
    Добавлена поддержка ознакомительного режима (is_guest).
    """
    keyboard = []

    # 1. ряд: бесконечная карусель фото (оставляем твои оригинальные эмодзи и текст)
    if img_total > 1:
        prev_idx = (img_index - 1 + img_total) % img_total
        next_idx = (img_index + 1) % img_total
        btn_prev = InlineKeyboardButton("◀️ Пред.", callback_data=f"{CB_PREFIX_PROD_IMG}{product_id}_{prev_idx}")
        btn_next = InlineKeyboardButton("След. ▶️", callback_data=f"{CB_PREFIX_PROD_IMG}{product_id}_{next_idx}")
        counter_btn = InlineKeyboardButton(f"{img_index + 1} / {img_total}", callback_data=f"{CB_PREFIX_IMG_GRID}{product_id}_{category}")
        keyboard.append([btn_prev, counter_btn, btn_next])

    # 2. ряд: читать описание и рецепт (динамически)
    drink_keywords = ['кофе', 'чай', 'дрип', 'зерно', 'молотый', 'эспрессо', 'фильтр', 'пуэр', 'улун']
    black_list = ['мерч', 'аксессуары', 'кружка', 'шоппер', 'кепка', 'gear']
    current_cat_low = category.lower()
    is_drink = any(k in current_cat_low for k in drink_keywords) and not any(k in current_cat_low for k in black_list)

    row_ext = []
    if has_overflow:
        row_ext.append(InlineKeyboardButton("📖 Читать описание", callback_data=f"{CB_READ_FULL_DESC}{product_id}"))

    # Рецепты показываем только авторизованным (бонус за регистрацию)
    if not is_guest and is_drink and (details_shown or has_overflow):
        btn_text = "🍵 Рецепт чая" if "чай" in current_cat_low else "☕️ Как заварить?"
        row_ext.append(InlineKeyboardButton(btn_text, callback_data=f"{CB_BREW_GUIDE}{product_id}"))

    if row_ext:
        keyboard.append(row_ext)

    # 3. ряд: управление количеством (скрываем для гостя)
    if not is_guest:
        keyboard.append([
            InlineKeyboardButton("➖", callback_data=f"{CB_PREFIX_CHANGE_QUANTITY}dec_{product_id}_{category}"),
            InlineKeyboardButton(f"{quantity} шт.", callback_data=f"{CB_PREFIX_QTY_GRID}{product_id}_{category}"),
            InlineKeyboardButton("➕", callback_data=f"{CB_PREFIX_CHANGE_QUANTITY}inc_{product_id}_{category}")
        ])

    # 4. ряд: детализация и тумблер избранного
    det_state = "det" if details_shown else "nodet"
    if details_shown:
        details_btn = InlineKeyboardButton("Скрыть детали 🔼", callback_data=f"{CB_PREFIX_SELECT_PRODUCT}{product_id}_{category}")
    else:
        details_btn = InlineKeyboardButton("Подробнее 📖", callback_data=f"{CB_PREFIX_SELECT_PRODUCT}{product_id}_{category}_details")

    if is_guest:
        # Гость может видеть детали, но не может ставить лайки
        keyboard.append([details_btn])
    else:
        fav_icon = "❤️" if is_favorite else "🤍"
        keyboard.append([details_btn, InlineKeyboardButton(fav_icon, callback_data=f"{CB_PREFIX_TOGGLE_FAV}{product_id}_{category}_{det_state}")])

    # 5. ряд: кнопка действия
    if is_guest:
        # Для гостя — единственная кнопка призыва к регистрации
        keyboard.append([InlineKeyboardButton("✨ Начать регистрацию", callback_data=CB_START_REGISTRATION)])
    elif category != "cartedit":
        # Обычный режим добавления в корзину для авторизованных
        keyboard.append([InlineKeyboardButton(f"🛒 Добавить в корзину ({quantity} шт.)", callback_data=f"{CB_ADD_TO_CART}{product_id}")])

    # 6. ряд: контекстная навигация назад (доступна всем)
    if category == "cartedit":
        keyboard.append([InlineKeyboardButton("⬅️ Назад в редактор корзины", callback_data=CB_EDIT_CART)])
    elif category == "fav":
        keyboard.append([InlineKeyboardButton("⬅️ Назад в избранное", callback_data=CB_FAVORITES_MENU)])
    else:
        keyboard.append([InlineKeyboardButton("⬅️ Назад к списку", callback_data=f"{CB_BACK_TO_PRODUCT_LIST}{category}")])

    # 7. объединенный ряд: навигация в избранное и корзину (скрываем для гостя)
    if not is_guest:
        nav_row =[]
        if is_favorite:
            nav_row.append(InlineKeyboardButton("❤️ В избранное", callback_data=CB_FAVORITES_MENU))
        if cart:
            cart_text = "🛒 В корзину" if is_favorite else "🛒 Перейти в корзину"
            nav_row.append(InlineKeyboardButton(cart_text, callback_data=CB_VIEW_CART))
        if nav_row:
            keyboard.append(nav_row)

    # 8. ряд: финальный выход (для юзера — меню, для гостя ничего не добавляем, так как кнопка регистрации уже есть выше)
    if not is_guest:
        keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data=CB_USER_SHOW_MAIN_MENU)])

    return InlineKeyboardMarkup(keyboard)


def get_recipe_view_keyboard(product_id: int, category: str, is_saved: bool = False) -> InlineKeyboardMarkup:
    """
    Клавиатура режима просмотра рецепта.
    Если рецепт сохранен, кнопка сохранения исчезает.
    """
    keyboard = []

    # Кнопку сохранения показываем только если еще не сохранено
    if not is_saved:
        keyboard.append([InlineKeyboardButton("⭐ Сохранить рецепт", callback_data=f"{CB_RECIPE_SAVE}{product_id}")])

    # Навигационный ряд (остается всегда)
    keyboard.append([
        InlineKeyboardButton("⬅️ К товару", callback_data=f"{CB_PREFIX_SELECT_PRODUCT}{product_id}_{category}_details"),
        InlineKeyboardButton("🏠 Главное меню", callback_data=CB_USER_SHOW_MAIN_MENU)
    ])

    return InlineKeyboardMarkup(keyboard)


def get_quantity_grid_keyboard(product_id: int, category: str) -> InlineKeyboardMarkup:
    """Создает сетку выбора количества."""
    keyboard = [
        [
            InlineKeyboardButton("3 шт.", callback_data=f"{CB_PREFIX_SET_QTY}{product_id}_{category}_3"),
            InlineKeyboardButton("6 шт.", callback_data=f"{CB_PREFIX_SET_QTY}{product_id}_{category}_6")
        ],
        [
            InlineKeyboardButton("9 шт.", callback_data=f"{CB_PREFIX_SET_QTY}{product_id}_{category}_9"),
            InlineKeyboardButton("15 шт.", callback_data=f"{CB_PREFIX_SET_QTY}{product_id}_{category}_15")
        ],
        [InlineKeyboardButton("🗑 Очистить (удалить)", callback_data=f"{CB_PRODUCT_CLEAR}{product_id}_{category}")],
        [InlineKeyboardButton("⬅️ Назад к карточке", callback_data=f"{CB_PREFIX_SELECT_PRODUCT}{product_id}_{category}")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_favorites_hub_keyboard(products_count: int, recipes_count: int) -> InlineKeyboardMarkup:
    """Главное меню раздела Избранное."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🛍 Сохранённые товары ({products_count})", callback_data=CB_FAV_PRODUCTS_LIST)],
        [InlineKeyboardButton(f"📜 Сохранённые рецепты ({recipes_count})", callback_data=CB_FAV_RECIPES_LIST)],
        [InlineKeyboardButton("🏠 Главное меню", callback_data=CB_USER_SHOW_MAIN_MENU)]
    ])


def get_favorites_list_keyboard(favorites_data: List[dict[str, Any]], cart: dict[str, Any], deleted_id: Optional[int] = None, timer: int = 5) -> InlineKeyboardMarkup:
    """Компактная клавиатура списка товаров в избранном."""
    keyboard = []

    for item in favorites_data:
        product = item['product']
        is_avail = item['is_available']
        p_id_str = str(product.id)

        # Логика анимации удаления
        if deleted_id and product.id == deleted_id:
            keyboard.append([InlineKeyboardButton(f"↩️ Вернуть ({timer}с): {product.name}", callback_data=f"{CB_FAV_UNDO_RM}{product.id}")])
            continue

        # Ряд 1: название
        keyboard.append([InlineKeyboardButton(f"☕️ {product.name}", callback_data=f"{CB_PREFIX_SELECT_PRODUCT}{product.id}_fav")])

        # Ряд 2: управление
        if is_avail:
            qty_in_cart = cart.get(p_id_str, {}).get('quantity', 0)
            if qty_in_cart > 0:
                action_row = [
                    InlineKeyboardButton("➖", callback_data=f"{CB_FAV_DEC_CART}{product.id}"),
                    InlineKeyboardButton(f"{qty_in_cart} шт.", callback_data=f"{CB_PREFIX_FAV_QTY_GRID}{product.id}"),
                    InlineKeyboardButton("➕", callback_data=f"{CB_FAV_INC_CART}{product.id}"),
                    InlineKeyboardButton("❌", callback_data=f"{CB_PREFIX_RM_FAV}{product.id}")
                ]
            else:
                action_row = [
                    InlineKeyboardButton("🛒 В корзину", callback_data=f"{CB_FAV_ADD_CART}{product.id}"),
                    InlineKeyboardButton("❌ Удалить", callback_data=f"{CB_PREFIX_RM_FAV}{product.id}")
                ]
            keyboard.append(action_row)
        else:
            status_icon = "🔔" if item['notify_status'] else "🔕"
            keyboard.append([
                InlineKeyboardButton(f"{status_icon} Сообщить", callback_data=f"{CB_PREFIX_NOTIFY_FAV}{product.id}"),
                InlineKeyboardButton("❌ Удалить", callback_data=f"{CB_PREFIX_RM_FAV}{product.id}")
            ])

    # Системные кнопки
    if cart:
        keyboard.append([InlineKeyboardButton("🛒 Перейти в корзину", callback_data=CB_VIEW_CART)])

    # [новое] назад в хаб избранного
    keyboard.append([InlineKeyboardButton("⬅️ Назад в Избранное", callback_data=CB_FAVORITES_MENU)])
    keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data=CB_USER_SHOW_MAIN_MENU)])

    return InlineKeyboardMarkup(keyboard)


def get_fav_quantity_grid_keyboard(product_id: int) -> InlineKeyboardMarkup:
    """Создает сетку выбора количества для меню Избранного."""
    keyboard = [
        [
            InlineKeyboardButton("3 шт.", callback_data=f"{CB_PREFIX_FAV_SET_QTY}{product_id}_3"),
            InlineKeyboardButton("6 шт.", callback_data=f"{CB_PREFIX_FAV_SET_QTY}{product_id}_6")
        ],
        [
            InlineKeyboardButton("9 шт.", callback_data=f"{CB_PREFIX_FAV_SET_QTY}{product_id}_9"),
            InlineKeyboardButton("15 шт.", callback_data=f"{CB_PREFIX_FAV_SET_QTY}{product_id}_15")
        ],
        [InlineKeyboardButton("🗑 Убрать из корзины", callback_data=f"{CB_FAV_CART_CLEAR}{product_id}")],
        [InlineKeyboardButton("⬅️ Назад к списку", callback_data=CB_FAVORITES_MENU)]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_cart_keyboard(cart: dict[str, Any], is_staff: bool = False) -> InlineKeyboardMarkup:
    keyboard = []
    if cart:
        # [новое] кнопка редактирования самым первым рядом
        keyboard.append([
            InlineKeyboardButton("✏️ Редактировать / Удалить товары", callback_data=CB_EDIT_CART)
        ])

        keyboard.append([
            InlineKeyboardButton("✅ Оформить заказ", callback_data=CB_CHECKOUT),
            InlineKeyboardButton("🗑️ Очистить корзину", callback_data=CB_CLEAR_CART)
        ])

    keyboard.append([InlineKeyboardButton("⬅️ Назад к категориям", callback_data=CB_BACK_TO_CATEGORIES)])

    return InlineKeyboardMarkup(keyboard)

# 2. клавиатура режима редактирования
def get_cart_edit_keyboard(cart: dict[str, Any], products_dict: dict[str, Any], deleted_id: Optional[int] = None, deleted_qty: int = 0, timer: int = 5) -> InlineKeyboardMarkup:
    """Улучшенная клавиатура редактора корзины."""
    keyboard = []

    if deleted_id is not None and str(deleted_id) in products_dict:
        p_name = products_dict[str(deleted_id)].name
        keyboard.append([
            InlineKeyboardButton(f"↩️ Вернуть ({timer}с): {p_name}", callback_data=f"{CB_CART_UNDO_RM}{deleted_id}")
        ])

    for p_id_str, item in sorted(cart.items(), key=lambda x:
        int(x[0])):
        p_id = int(p_id_str)
        product = products_dict.get(str(p_id))
        if not product:
            continue

        qty = item['quantity']
        price = float(item['price'])
        sum_price = int(price * qty)

        # Ряд 1: название
        keyboard.append([InlineKeyboardButton(f"📦 {product.name} 🔎", callback_data=f"{CB_PREFIX_SELECT_PRODUCT}{p_id}_cartedit")])

        # Ряд 2: управление
        row = [
            InlineKeyboardButton("➖", callback_data=f"{CB_PREFIX_CART_DEC}{p_id}"),
            # Теперь кнопка вызывает сетку пресетов
            InlineKeyboardButton(f"{qty} шт. ({sum_price}₽)", callback_data=f"{CB_PREFIX_CART_QTY_GRID}{p_id}"),
            InlineKeyboardButton("➕", callback_data=f"{CB_PREFIX_CART_INC}{p_id}"),
            InlineKeyboardButton("❌", callback_data=f"{CB_PREFIX_CART_DEL}{p_id}")
        ]
        keyboard.append(row)

    keyboard.append([InlineKeyboardButton("✅ Готово (Вернуться к итогу)", callback_data=CB_BACK_TO_CART_SUMMARY)])
    return InlineKeyboardMarkup(keyboard)

def get_cart_quantity_grid_keyboard(product_id: int) -> InlineKeyboardMarkup:
    """Сетка выбора количества для редактора корзины."""
    keyboard = [
        [
            InlineKeyboardButton("3 шт.", callback_data=f"{CB_PREFIX_CART_SET_QTY}{product_id}_3"),
            InlineKeyboardButton("6 шт.", callback_data=f"{CB_PREFIX_CART_SET_QTY}{product_id}_6")
        ],
        [
            InlineKeyboardButton("9 шт.", callback_data=f"{CB_PREFIX_CART_SET_QTY}{product_id}_9"),
            InlineKeyboardButton("15 шт.", callback_data=f"{CB_PREFIX_CART_SET_QTY}{product_id}_15")
        ],
        # Кнопка возврата ведет обратно в редактор корзины
        [InlineKeyboardButton("⬅️ Назад к редактору", callback_data=CB_EDIT_CART)]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_admin_main_keyboard(unread_messages_count: int = 0) -> InlineKeyboardMarkup:
    """Главное меню админ-панели."""

    comms_button_text = "📬 Сообщения"
    if unread_messages_count > 0:
        comms_button_text += f" ({unread_messages_count} новых)"

    keyboard = [
        [InlineKeyboardButton(comms_button_text, callback_data=CB_ADMIN_COMMUNICATION_CENTER)],
        [InlineKeyboardButton("👥 Управление пользователями", callback_data=CB_ADMIN_USERS)],
        [InlineKeyboardButton("🧾 Управление заказами", callback_data=CB_ADMIN_ORDERS_MENU)],
        [
            InlineKeyboardButton("📊 Статистика", callback_data=CB_ADMIN_STATS),
            InlineKeyboardButton("⚙️ Настройки", callback_data=CB_ADMIN_SETTINGS)
        ],
        # Кнопка назад ведет в "меню персонала" (товары/профиль/панель)
        [InlineKeyboardButton("⬅️ Назад", callback_data=CB_ADMIN_BACK_TO_STAFF_MENU)],

        # Изменение: вместо "закрыть" -> "главное меню" (клиентское)
        [InlineKeyboardButton("🏠 Главное меню", callback_data=CB_USER_SHOW_MAIN_MENU)],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_admin_orders_menu_keyboard(counts: Dict[OrderStatus, int]) -> InlineKeyboardMarkup:
    """Создает клавиатуру для меню управления заказами с фильтрами по статусам."""

    button_map = {
        OrderStatus.ACCEPTED: "🆕 Новые (Приняты)",
        OrderStatus.AWAITING_PAYMENT: "⌛️ Ожидают оплаты",
        OrderStatus.PAID: "✅ Оплаченные",
        OrderStatus.SHIPPED: "🚚 В пути",
        OrderStatus.READY_FOR_PICKUP: "📦 Готовы к выдаче",
        OrderStatus.COMPLETED: "🏁 Завершённые",
        OrderStatus.CANCELLED: "❌ Отменённые"
    }

    keyboard = []
    for status, text in button_map.items():
        count = counts.get(status, 0)
        keyboard.append([
            InlineKeyboardButton(f"{text} ({count})", callback_data=f"{CB_PREFIX_ORDERS_BY_STATUS}{status.name}")
        ])

    keyboard.append([InlineKeyboardButton("⬅️ Назад в панель", callback_data=CB_ADMIN_BACK_TO_MAIN)])
    return InlineKeyboardMarkup(keyboard)


def get_order_list_keyboard(orders: List[Order], status_name: str) -> InlineKeyboardMarkup:
    """Создает клавиатуру со списком заказов."""
    keyboard = []
    for order in orders:
        text = f"Заказ #{order.id} от {order.created_at.strftime('%d.%m %H:%M')}"
        keyboard.append([
            InlineKeyboardButton(text, callback_data=f"{CB_PREFIX_ORDER_DETAILS}{order.id}_{status_name}")
        ])
    keyboard.append([InlineKeyboardButton("⬅️ Назад к статусам", callback_data=CB_ADMIN_ORDERS_MENU)])
    return InlineKeyboardMarkup(keyboard)


def get_order_details_keyboard(order: Order, source_list: str) -> InlineKeyboardMarkup:
    """Создает клавиатуру с действиями для конкретного заказа."""
    keyboard = []
    order_id = order.id

    # 1. ожидает оплаты -> оплачен
    if order.status == OrderStatus.AWAITING_PAYMENT:
        keyboard.append([
            InlineKeyboardButton("✅ Подтвердить оплату", callback_data=f"{CB_PREFIX_ORDER_ACTION}set_paid_{order_id}"),
            InlineKeyboardButton("❌ Отменить", callback_data=f"{CB_PREFIX_ORDER_ACTION}set_cancelled_{order_id}")
        ])

    # 2. оплачен -> в доставку (shipped)
    elif order.status == OrderStatus.PAID:
        keyboard.append([
            InlineKeyboardButton("🚚 Передать в доставку", callback_data=f"{CB_PREFIX_ORDER_ACTION}set_shipped_{order_id}")
        ])

    # 3. в доставке -> готов к выдаче (пвз) или завершен (если курьер отдал)
    elif order.status == OrderStatus.SHIPPED:
        keyboard.append([
            InlineKeyboardButton("🏢 Прибыл в ПВЗ (Готов)", callback_data=f"{CB_PREFIX_ORDER_ACTION}set_ready_{order_id}"),
            InlineKeyboardButton("🏁 Доставлен (Завершить)", callback_data=f"{CB_PREFIX_ORDER_ACTION}set_completed_{order_id}")
        ])

    # 4. готов к выдаче -> завершен (клиент забрал)
    elif order.status == OrderStatus.READY_FOR_PICKUP:
        keyboard.append([
            InlineKeyboardButton("🏁 Выдан (Завершить)", callback_data=f"{CB_PREFIX_ORDER_ACTION}set_completed_{order_id}")
        ])

    keyboard.append([InlineKeyboardButton("⬅️ Назад к списку", callback_data=f"{CB_PREFIX_ORDERS_BY_STATUS}{source_list}")])
    return InlineKeyboardMarkup(keyboard)


def get_admin_users_keyboard(
    pending_count: int, approved_count: int, blocked_count: int,
    user_count: int, manager_count: int, admin_count: int
) -> InlineKeyboardMarkup:
    """Меню управления пользователями с разбивкой по статусам и ролям."""
    keyboard = [
        # Фильтры по статусу
        [
            InlineKeyboardButton(f"⌛️ В ожидании ({pending_count})", callback_data=f"{CB_PREFIX_USERS_BY_STATUS}pending"),
            InlineKeyboardButton(f"✅ Одобренные ({approved_count})", callback_data=f"{CB_PREFIX_USERS_BY_STATUS}approved")
        ],
        [
            InlineKeyboardButton(f"🚫 Заблокированные ({blocked_count})", callback_data=f"{CB_PREFIX_USERS_BY_STATUS}blocked")
        ],
        # Фильтры по ролям
        [
            InlineKeyboardButton(f"👤 Пользователи ({user_count})", callback_data=f"{CB_PREFIX_USERS_BY_ROLE}user"),
            InlineKeyboardButton(f"👨‍💼 Менеджеры ({manager_count})", callback_data=f"{CB_PREFIX_USERS_BY_ROLE}manager")
        ],
        [
            InlineKeyboardButton(f"👑 Администраторы ({admin_count})", callback_data=f"{CB_PREFIX_USERS_BY_ROLE}admin")
        ],
        # Навигация
        [InlineKeyboardButton("⬅️ Назад", callback_data=CB_ADMIN_BACK_TO_MAIN)],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_user_list_keyboard(users: List[User], status: str) -> InlineKeyboardMarkup:
    """Клавиатура со списком пользователей."""
    keyboard = []
    for user in users:
        keyboard.append([
            InlineKeyboardButton(user.fio, callback_data=f"{CB_PREFIX_USER_DETAILS}{user.id}_{status}")
        ])
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data=CB_ADMIN_USERS)])
    return InlineKeyboardMarkup(keyboard)


def get_user_details_keyboard(user: User, source_list: str, super_admin_ids: Optional[list[Any]] = None) -> InlineKeyboardMarkup:
    """Создает клавиатуру с иерархией ролей и защитой Супер-админов."""
    keyboard = []
    user_id = user.id
    super_admin_ids = super_admin_ids or []

    # Проверка: является ли текущий просматриваемый пользователь супер-админом?
    is_target_super = user.telegram_id in super_admin_ids

    if user.status == UserStatus.PENDING:
        keyboard.append([
            InlineKeyboardButton("✅ Одобрить", callback_data=f"{CB_PREFIX_USER_ACTION}approve_{user_id}"),
            InlineKeyboardButton("🚫 Отклонить (Блок)", callback_data=f"{CB_PREFIX_USER_ACTION}block_{user_id}"),
        ])
    elif user.status == UserStatus.APPROVED:
        # Блок управления ролями
        if user.role == UserRole.USER:
            keyboard.append([InlineKeyboardButton("⬆️ Сделать Менеджером", callback_data=f"{CB_PREFIX_USER_ACTION}promote_manager_{user_id}")])

        elif user.role == UserRole.MANAGER:
            keyboard.append([
                InlineKeyboardButton("⬆️ Сделать Администратором", callback_data=f"{CB_PREFIX_USER_ACTION}promote_admin_{user_id}"),
                InlineKeyboardButton("⬇️ Понизить до Пользователя", callback_data=f"{CB_PREFIX_USER_ACTION}demote_user_{user_id}")
            ])

        elif user.role == UserRole.ADMIN:
            # Обычного админа можно понизить до менеджера, если он не супер
            if not is_target_super:
                keyboard.append([InlineKeyboardButton("⬇️ Понизить до Менеджера", callback_data=f"{CB_PREFIX_USER_ACTION}demote_manager_{user_id}")])

        # Блок опасных действий (скрыт для супер-админов)
        if not is_target_super:
            keyboard.append([InlineKeyboardButton("♻️ Удалить регистрацию (Сброс)", callback_data=f"{CB_PREFIX_USER_ACTION}reset_{user_id}")])
            keyboard.append([InlineKeyboardButton("🚫 Заблокировать", callback_data=f"{CB_PREFIX_USER_ACTION}block_{user_id}")])

    elif user.status == UserStatus.BLOCKED:
        keyboard.append([InlineKeyboardButton("✅ Разблокировать", callback_data=f"{CB_PREFIX_USER_ACTION}approve_{user_id}")])

    keyboard.append([InlineKeyboardButton("🗑 GDPR-удаление (анонимизация)", callback_data=f"{CB_PREFIX_USER_ACTION}gdpr_delete_{user_id}")])

    # Кнопка назад (с исправлением из прошлого шага)
    if source_list.startswith("role_"):
        back_callback = f"{CB_PREFIX_USERS_BY_ROLE}{source_list.replace('role_', '')}"
    else:
        back_callback = f"{CB_PREFIX_USERS_BY_STATUS}{source_list}"

    keyboard.append([InlineKeyboardButton("⬅️ Назад к списку", callback_data=back_callback)])
    return InlineKeyboardMarkup(keyboard)


def get_admin_settings_keyboard(is_auto_approve_enabled: bool) -> InlineKeyboardMarkup:
    """
    Обновленное меню настроек.
    Кнопка Proxy вынесена на самый верх для заметности.
    """
    auto_text = "✅ Авто-рег: ВКЛ" if is_auto_approve_enabled else "❌ Авто-рег: ВЫКЛ"

    keyboard = [
        # Кнопка proxy идет первой, чтобы ты её точно увидел
        [InlineKeyboardButton("🌐 Настройка Proxy / VPN", callback_data=CB_ADMIN_PROXY_MGMT)],

        [InlineKeyboardButton("🖼 Логотип регистрации", callback_data=CB_ADMIN_LOGO_MGMT)],
        [InlineKeyboardButton("🏃 Пункты самовывоза", callback_data=CB_ADMIN_PICKUP_MGMT)],
        [InlineKeyboardButton("🚚 Курьерская служба", callback_data=CB_ADMIN_COURIER_MGMT)],
        [InlineKeyboardButton("🟡 Яндекс.Доставка", callback_data=CB_ADMIN_SETUP_YANDEX)],
        [InlineKeyboardButton(auto_text, callback_data=CB_ADMIN_TOGGLE_AUTO_APPROVE)],
        [InlineKeyboardButton("🔄 Синхронизация товаров", callback_data=CB_ADMIN_SYNC_PRODUCTS)],
        [InlineKeyboardButton("⬅️ Назад", callback_data=CB_ADMIN_BACK_TO_MAIN)],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_admin_pickup_mgmt_keyboard(points: list[Any]) -> InlineKeyboardMarkup:
    """Список всех точек с индикацией статуса."""
    keyboard = []
    for idx, pt in enumerate(points):
        status_icon = "✅" if pt.get('is_active', True) else "❌"
        # [исправлено] используем cb_prefix_admin_pickup_view
        keyboard.append([InlineKeyboardButton(
            f"{status_icon} {pt['name']}",
            callback_data=f"{CB_PREFIX_ADMIN_PICKUP_VIEW}{idx}"
        )])

    keyboard.append([InlineKeyboardButton("➕ Добавить новый пункт", callback_data=CB_ADMIN_PICKUP_ADD)])
    keyboard.append([InlineKeyboardButton("⬅️ Назад в настройки", callback_data=CB_ADMIN_SETTINGS)])
    return InlineKeyboardMarkup(keyboard)

def get_pickup_item_edit_keyboard(idx: int, is_active: bool) -> InlineKeyboardMarkup:
    toggle_text = "🔴 Скрыть (Выключить)" if is_active else "🟢 Показать (Включить)"
    keyboard = [
        [InlineKeyboardButton(toggle_text, callback_data=f"{CB_PREFIX_ADMIN_PICKUP_TOGGLE}{idx}")],
        [
            InlineKeyboardButton("📝 Название", callback_data=f"{CB_ADMIN_PICKUP_EDIT}name_{idx}"),
            InlineKeyboardButton("📍 Адрес", callback_data=f"{CB_ADMIN_PICKUP_EDIT}address_{idx}")
        ],
        [
            InlineKeyboardButton("🕒 График", callback_data=f"{CB_ADMIN_PICKUP_EDIT}schedule_{idx}"),
            InlineKeyboardButton("⏱ Срок (дни)", callback_data=f"{CB_ADMIN_PICKUP_EDIT}days_{idx}")
        ],
        # [новое] ряд координат
        [InlineKeyboardButton("🌐 Координаты (Карта)", callback_data=f"{CB_ADMIN_PICKUP_EDIT}coords_{idx}")],
        [InlineKeyboardButton("🗑 Удалить пункт", callback_data=f"{CB_PREFIX_ADMIN_PICKUP_DEL}{idx}")],
        [InlineKeyboardButton("⬅️ Назад к списку", callback_data=CB_ADMIN_PICKUP_MGMT)]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_admin_courier_mgmt_keyboard(enabled: bool, cities: list[Any]) -> InlineKeyboardMarkup:
    """Меню управления курьерской доставкой."""
    status_text = "✅ Служба включена" if enabled else "❌ Служба выключена"
    keyboard = [[InlineKeyboardButton(status_text, callback_data=CB_ADMIN_COURIER_TOGGLE)]]

    # Список городов для удаления
    for city in cities:
        keyboard.append([
            InlineKeyboardButton(f"❌ {city['name']} ({city['cost']}₽)", callback_data=f"{CB_ADMIN_COURIER_DEL_CITY}{city['name']}")
        ])

    keyboard.append([InlineKeyboardButton("➕ Добавить город", callback_data=CB_ADMIN_COURIER_ADD_CITY)])
    keyboard.append([InlineKeyboardButton("⬅️ Назад в настройки", callback_data=CB_ADMIN_SETTINGS)])
    return InlineKeyboardMarkup(keyboard)


def get_yandex_confirm_keyboard(station_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💾 Сохранить этот склад", callback_data=f"{CB_ADMIN_SAVE_YANDEX}{station_id}")],
        [InlineKeyboardButton("⬅️ Отмена", callback_data=CB_ADMIN_SETTINGS)]
    ])


def get_threads_list_keyboard(threads: list[Any]) -> InlineKeyboardMarkup:
    """Отображает список чатов с понятными заголовками."""
    keyboard = []
    for thread in threads:
        markers = ""
        if thread.is_important:
            markers += "❗️"
        if not thread.is_read:
            markers += "🔵"

        # Логика заголовка
        if thread.order_id:
            text = f"{markers} Чат по заказу #{thread.order_id}"
        else:
            text = f"{markers} 💬 Консультация"

        keyboard.append([InlineKeyboardButton(text, callback_data=f"{CB_PREFIX_THREAD_DETAILS}{thread.id}")])

    keyboard.append([InlineKeyboardButton("⬅️ Назад в панель", callback_data=CB_ADMIN_BACK_TO_MAIN)])
    return InlineKeyboardMarkup(keyboard)


def get_thread_view_keyboard(thread: CommunicationThread, current_page: int = 0, total_pages: int = 1) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру для управления чатом с пагинацией.
    Page 0 = Самые новые. Page N = Самые старые.
    """

    important_text = "💔 Снять важность" if thread.is_important else "❗️ Пометить важным"

    keyboard = []

    # 1. навигация по истории (если страниц > 1)
    nav_row = []
    # Кнопка "раньше" (идем вглубь истории, увеличиваем индекс страницы)
    if current_page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("⬅️ Раньше", callback_data=f"{CB_PREFIX_THREAD_PAGE}{thread.id}_{current_page + 1}"))

    # Индикатор
    if total_pages > 1:
        nav_row.append(InlineKeyboardButton(f"{current_page + 1}/{total_pages}", callback_data="noop"))

    # Кнопка "позже" (идем к новым, уменьшаем индекс)
    if current_page > 0:
        nav_row.append(InlineKeyboardButton("Позже ➡️", callback_data=f"{CB_PREFIX_THREAD_PAGE}{thread.id}_{current_page - 1}"))

    if nav_row:
        keyboard.append(nav_row)

    # 2. действия
    keyboard.append([InlineKeyboardButton("↪️ Ответить", callback_data=f"{CB_PREFIX_THREAD_ACTION}reply_{thread.id}")])
    keyboard.append([
        InlineKeyboardButton(important_text, callback_data=f"{CB_PREFIX_THREAD_ACTION}toggle_important_{thread.id}"),
        InlineKeyboardButton("🔵 Пометить непрочитанным", callback_data=f"{CB_PREFIX_THREAD_ACTION}mark_unread_{thread.id}")
    ])
    keyboard.append([InlineKeyboardButton("⬅️ Назад к списку", callback_data=CB_ADMIN_COMMUNICATION_CENTER)])

    return InlineKeyboardMarkup(keyboard)


def get_user_main_keyboard(is_staff: bool = False, is_cart_empty: bool = True, has_favorites: bool = False) -> InlineKeyboardMarkup:
    """
    Главное меню пользователя с оптимизированной сеткой (2 кнопки в ряд для заказов/настроек).
    Реализован динамический ряд для Избранного и Корзины.
    """
    keyboard = []

    # 1. ряд: каталог (широкая кнопка)
    keyboard.append([InlineKeyboardButton("🛍️ Каталог товаров", callback_data=CB_USER_START_ORDERING)])

    # 2. ряд: личный кабинет (заказы + настройки)
    keyboard.append([
        InlineKeyboardButton("📦 Мои заказы", callback_data=CB_USER_MY_ORDERS),
        InlineKeyboardButton("⚙️ Настройки", callback_data=CB_USER_SETTINGS)
    ])

    # 3. ряд: динамическая навигация (избранное + корзина)
    system_row = []
    if has_favorites:
        system_row.append(InlineKeyboardButton("❤️ Избранное", callback_data=CB_FAVORITES_MENU))

    if not is_cart_empty:
        # Укорачиваем текст, если кнопок две, чтобы они влезли в одну строку
        cart_text = "🛒 Корзина" if has_favorites else "🛒 Перейти в корзину"
        system_row.append(InlineKeyboardButton(cart_text, callback_data=CB_VIEW_CART))

    if system_row:
        keyboard.append(system_row)

    # 4. ряд: о нас (широкая кнопка)
    keyboard.append([InlineKeyboardButton("ℹ️ О нас / Контакты", callback_data=CB_INFO_MENU)])

    # 5. ряд: ai помощник (акцентная кнопка)
    keyboard.append([InlineKeyboardButton("🤖 Спросить у AI (Бариста)", callback_data=CB_AI_CHAT_START)])

    # 6. ряд: админ-панель (только для персонала)
    if is_staff:
        keyboard.append([InlineKeyboardButton("🗂 Панель управления", callback_data=CB_STAFF_PANEL)])

    logger.info(f"Main menu generated for user. Staff: {is_staff}, Favs: {has_favorites}, CartEmpty: {is_cart_empty}")
    return InlineKeyboardMarkup(keyboard)

def get_ai_chat_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура управления внутри чата с AI. Только История и Главное меню."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📜 История сообщений", callback_data=CB_AI_CHAT_HISTORY)],
        [InlineKeyboardButton("🏠 Главное меню", callback_data=CB_USER_SHOW_MAIN_MENU)]
    ])


def get_cms_item_options_keyboard(item_id: int, parent_id: Optional[int]) -> InlineKeyboardMarkup:
    """Меню действий с пунктом в списке."""
    back_cb = f"{CB_PREFIX_INFO_GO}{parent_id if parent_id else 'root'}"

    keyboard = [
        [
            InlineKeyboardButton("⬆️", callback_data=f"{CB_CMS_MOVE_UP}{item_id}"),
            InlineKeyboardButton("⬇️", callback_data=f"{CB_CMS_MOVE_DOWN}{item_id}")
        ],
        [InlineKeyboardButton("🅰️ Переименовать", callback_data=f"{CB_CMS_RENAME}{item_id}")],
        [InlineKeyboardButton("❌ Удалить", callback_data=f"{CB_PREFIX_INFO_DEL}{item_id}")],
        [InlineKeyboardButton("⬅️ Назад к списку", callback_data=back_cb)]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_cms_keyboard(
    items: List[dict[str, Any]],
    current_page_id: Optional[int],
    parent_id: Optional[int],
    is_staff: bool,
    edit_mode: bool = False
) -> InlineKeyboardMarkup:
    keyboard = []

    # 1. список подразделов
    for item in items:
        title = item['title']
        item_id = item['id']

        if edit_mode:
            # Режим правки
            keyboard.append([
                InlineKeyboardButton(f"⚙️ {title}", callback_data=f"{CB_CMS_ITEM_OPTS}{item_id}")
            ])
        else:
            # Обычный режим
            icon = "📁" if not item['body_text'] and not item['image_id'] else "📄"
            keyboard.append([
                InlineKeyboardButton(f"{icon} {title}", callback_data=f"{CB_PREFIX_INFO_GO}{item_id}")
            ])

    # 2. кнопки управления (только для staff)
    if is_staff:
        ctrl_row = []
        # Кнопка создания
        ctrl_row.append(InlineKeyboardButton("➕ Создать", callback_data=f"{CB_PREFIX_INFO_ADD}{current_page_id if current_page_id else 'root'}"))

        # Кнопка режима правки (только если есть что править - т.е. есть дети)
        if items:
            mode_text = "✅ Завершить" if edit_mode else "⚙️ Режим правки"
            ctrl_row.append(InlineKeyboardButton(mode_text, callback_data=CB_CMS_MODE_TOGGLE))

        keyboard.append(ctrl_row)

        # Редактирование текущей страницы (если мы не в корне и не в режиме правки списка)
        if current_page_id and not edit_mode:
             keyboard.append([
                 InlineKeyboardButton("✏️ Ред. содержимое этой стр.", callback_data=f"{CB_PREFIX_INFO_EDIT}{current_page_id}")
             ])

    # 3. навигация
    if current_page_id:
        back_cb = f"{CB_PREFIX_INFO_GO}{parent_id}" if parent_id else CB_INFO_MENU
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data=back_cb)])
    else:
        keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data=CB_USER_SHOW_MAIN_MENU)])

    return InlineKeyboardMarkup(keyboard)

def get_user_orders_keyboard(orders: List[Order], bot_username: str, back_callback: str = CB_USER_SHOW_MAIN_MENU) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру со списком заказов пользователя.
    :param back_callback: Куда ведет кнопка 'Назад'. По умолчанию - в Главное меню.
    """
    keyboard = []
    for order in orders:
        text = f"Заказ #{order.id} от {order.created_at.strftime('%d.%m.%y')} - {order.status.value}"
        keyboard.append([
            InlineKeyboardButton(text, callback_data=f"{CB_PREFIX_USER_ORDER_DETAILS}{order.id}")
        ])

    # Используем динамический callback для возврата
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data=back_callback)])

    return InlineKeyboardMarkup(keyboard)


def get_cancellation_inline_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура при запросе причины отмены (Inline)."""
    keyboard = [
        [InlineKeyboardButton("❌ Отменить без указания причины", callback_data=CB_CANCEL_NO_REASON)],
        [InlineKeyboardButton("⬅️ Вернуться (Не отменять)", callback_data=CB_DONT_CANCEL)]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_after_cancellation_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура после успешной отмены."""
    keyboard = [
        [InlineKeyboardButton("📦 К моим заказам", callback_data=CB_USER_MY_ORDERS)],
        [InlineKeyboardButton("🏠 В главное меню", callback_data=CB_USER_SHOW_MAIN_MENU)]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_order_rating_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """Ряд кнопок со звездами для оценки заказа."""
    stars = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
    row = [InlineKeyboardButton(s, callback_data=f"{CB_USER_SET_RATING}{order_id}_{i+1}") for i, s in enumerate(stars)]

    keyboard = [
        row,
        [InlineKeyboardButton("⬅️ Назад к заказу", callback_data=f"{CB_PREFIX_USER_ORDER_DETAILS}{order_id}")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_user_order_details_keyboard(order: Order, bot_username: str, has_history: bool = False) -> InlineKeyboardMarkup:
    """Клавиатура для детального просмотра заказа пользователем."""
    keyboard = []

    # Кнопка оплаты (для неоплаченных)
    is_unpaid = order.status in [OrderStatus.ACCEPTED, OrderStatus.AWAITING_PAYMENT]
    if is_unpaid and order.payment_url:
        keyboard.append([InlineKeyboardButton("💳 Оплатить заказ", url=order.payment_url)])

    # Кнопка отмены (для неоплаченных)
    if is_unpaid:
        keyboard.append([InlineKeyboardButton("❌ Отменить заказ", callback_data=f"{CB_PREFIX_USER_CANCEL_ORDER}{order.id}")])

    # Показываем для всех статусов, кроме тех, что в процессе оформления (accepted/awaiting_payment)
    # Так как если он уже "принят", его не надо повторять, его надо оплатить.
    repeatable_statuses = [
        OrderStatus.PAID, OrderStatus.SHIPPED, OrderStatus.READY_FOR_PICKUP,
        OrderStatus.COMPLETED, OrderStatus.CANCELLED
    ]
    if order.status in repeatable_statuses:
        keyboard.append([InlineKeyboardButton("🔄 Повторить этот заказ", callback_data=f"{CB_REPEAT_ORDER}{order.id}")])

    # Кнопки управления комментариями к заказу
    # Если у заказа есть комментарий клиента (в поле gift_comment или новом поле), добавляем кнопки редактирования/удаления
    if hasattr(order, 'customer_comment') and order.customer_comment:
        # У заказа есть комментарий от клиента
        keyboard.append([
            InlineKeyboardButton("✏️ Редактировать комментарий", callback_data=f"{CB_USER_EDIT_COMMENT_ORDER}{order.id}"),
            InlineKeyboardButton("🗑️ Удалить комментарий", callback_data=f"{CB_USER_DELETE_COMMENT_ORDER}{order.id}")
        ])
    elif order.gift_comment:
        # Если есть подарочный комментарий, можно дать возможность редактировать/удалить и его
        keyboard.append([
            InlineKeyboardButton("✏️ Редактировать комментарий", callback_data=f"{CB_USER_EDIT_COMMENT_ORDER}{order.id}"),
            InlineKeyboardButton("🗑️ Удалить комментарий", callback_data=f"{CB_USER_DELETE_COMMENT_ORDER}{order.id}")
        ])
    else:
        # Если комментария нет, добавляем кнопку добавления
        keyboard.append([InlineKeyboardButton("💬 Добавить комментарий к заказу", callback_data=f"{CB_USER_ADD_COMMENT_ORDER}{order.id}")])

    keyboard.append([InlineKeyboardButton("💬 Связаться с поддержкой", callback_data=f"{CB_PREFIX_USER_CONTACT_SUPPORT}{order.id}")])
    if order.status in [OrderStatus.COMPLETED, OrderStatus.CANCELLED] and not order.rating:
        keyboard.insert(0, [InlineKeyboardButton("⭐ Оценить качество", callback_data=f"{CB_USER_RATE_ORDER_START}{order.id}")])
    if has_history:
        keyboard.append([InlineKeyboardButton("📜 История переписки", callback_data=f"{CB_USER_VIEW_THREAD}{order.id}")])

    keyboard.append([InlineKeyboardButton("⬅️ Назад к заказам", callback_data=CB_USER_MY_ORDERS)])
    keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data=CB_USER_SHOW_MAIN_MENU)])

    return InlineKeyboardMarkup(keyboard)


def get_user_welcome_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой 'Перейти в меню' после одобрения."""
    keyboard = [[InlineKeyboardButton("🎉 Перейти в меню", callback_data=CB_USER_SHOW_MAIN_MENU)]]
    return InlineKeyboardMarkup(keyboard)


def get_gallery_keyboard(
    product_id: int, current_index: int, total_count: int,
    cart: dict[str, Any], category: str, is_favorite: bool = False, quantity: int = 1
) -> InlineKeyboardMarkup:
    """
    Улучшенная клавиатура галереи.
    Полностью повторяет структуру карточки товара, но с навигацией по списку (1/29).
    """
    keyboard = []

    # 1. ряд: навигация между товарами (счетчик списка)
    if total_count > 1:
        keyboard.append([
            InlineKeyboardButton("⬅️", callback_data=CB_GALLERY_PREV),
            InlineKeyboardButton(f"{current_index + 1} / {total_count}", callback_data=CB_GALLERY_OPEN_LIST),
            InlineKeyboardButton("➡️", callback_data=CB_GALLERY_NEXT)
        ])

    # 2. ряд: управление количеством (как в карточке)
    keyboard.append([
        InlineKeyboardButton("➖", callback_data=f"{CB_PREFIX_CHANGE_QUANTITY}dec_{product_id}_{category}"),
        InlineKeyboardButton(f"{quantity} шт.", callback_data=f"{CB_PREFIX_QTY_GRID}{product_id}_{category}"),
        InlineKeyboardButton("➕", callback_data=f"{CB_PREFIX_CHANGE_QUANTITY}inc_{product_id}_{category}")
    ])

    # 3. ряд: подробнее и сердечко (favorites)
    fav_icon = "❤️" if is_favorite else "🤍"
    keyboard.append([
        InlineKeyboardButton("Подробнее 📖", callback_data=f"{CB_PREFIX_SELECT_PRODUCT}{product_id}_{category}_details"),
        InlineKeyboardButton(fav_icon, callback_data=f"{CB_PREFIX_TOGGLE_FAV}{product_id}_{category}_nodet")
    ])

    # 4. ряд: добавить в корзину (быстрое действие)
    keyboard.append([InlineKeyboardButton(f"🛒 Добавить в корзину ({quantity} шт.)", callback_data=f"{CB_GALLERY_ADD}_{product_id}")])

    # 5. ряд: системная навигация галереи
    keyboard.append([
        InlineKeyboardButton("⇅ Сортировка / Вид", callback_data=CB_OPEN_SORT_MENU),
        InlineKeyboardButton("⬅️ Назад к категориям", callback_data=CB_BACK_TO_CATEGORIES)
    ])

    # 6. ряд: объединенный ряд хабов (избранное + корзина)
    nav_row = []
    # Показываем хаб избранного, если там что-то есть (независимо от текущего товара)
    # Здесь мы полагаемся на логику отрисовщика, который передает состояние
    if is_favorite:
        # Или если передать флаг has_any_favs
        nav_row.append(InlineKeyboardButton("❤️ В избранное", callback_data=CB_FAVORITES_MENU))

    if cart:
        cart_text = "🛒 В корзину" if nav_row else "🛒 Перейти в корзину"
        nav_row.append(InlineKeyboardButton(cart_text, callback_data=CB_VIEW_CART))

    if nav_row:
        keyboard.append(nav_row)

    # 7. ряд: главное меню
    keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data=CB_USER_SHOW_MAIN_MENU)])

    return InlineKeyboardMarkup(keyboard)


def get_sort_menu_keyboard(current_sort: str, view_mode: str = 'list', has_sca_data: bool = True, is_guest: bool = False) -> InlineKeyboardMarkup:
    """
    Клавиатура настроек сортировки.
    Для гостей скрыт выбор режима 'Галерея', доступна только сортировка.
    """
    def txt(mode: str, label: str) -> Any:
        return f"✅ {label}" if current_sort == mode else label

    keyboard = []

    # [правило ios] 1. ряд выбора вида (список/галерея) — скрываем для гостей
    if not is_guest:
        keyboard.append([
            InlineKeyboardButton(f"{'✅' if view_mode == 'list' else ''} 📃 Список", callback_data=f"{CB_TOGGLE_VIEW}_list"),
            InlineKeyboardButton(f"{'✅' if view_mode == 'gallery' else ''} 🖼 Галерея", callback_data=f"{CB_TOGGLE_VIEW}_gallery")
        ])

    # 2. ряды сортировки (оставляем твой оригинальный код)
    keyboard.append([
        InlineKeyboardButton(txt('price_asc', "₽ Дешевле"), callback_data=f"{CB_PREFIX_SET_SORT}price_asc"),
        InlineKeyboardButton(txt('price_desc', "₽ Дороже"), callback_data=f"{CB_PREFIX_SET_SORT}price_desc")
    ])

    keyboard.append([
        InlineKeyboardButton(txt('name_asc', "🔤 А-Я"), callback_data=f"{CB_PREFIX_SET_SORT}name_asc"),
        InlineKeyboardButton(txt('name_desc', "🔤 Я-А"), callback_data=f"{CB_PREFIX_SET_SORT}name_desc")
    ])

    if has_sca_data:
        keyboard.append([
            InlineKeyboardButton(txt('sca_desc', "🏆 SCA (High)"), callback_data=f"{CB_PREFIX_SET_SORT}sca_desc"),
            InlineKeyboardButton(txt('sca_asc', "🥉 SCA (Low)"), callback_data=f"{CB_PREFIX_SET_SORT}sca_asc")
        ])

    # 3. навигация
    keyboard.append([InlineKeyboardButton("⬅️ Назад к товарам", callback_data=CB_BACK_TO_PRODUCT_LIST)])

    if is_guest:
        keyboard.append([InlineKeyboardButton("📝 Начать регистрацию", callback_data=CB_START_REGISTRATION)])

    return InlineKeyboardMarkup(keyboard)


def get_delivery_method_keyboard(courier_enabled: bool = False) -> InlineKeyboardMarkup:
    """Динамическая клавиатура выбора доставки."""
    keyboard = [
        [InlineKeyboardButton("🏃 Самовывоз", callback_data=CB_DELIVERY_TYPE_SELF)],
        [InlineKeyboardButton("🏢 ТК СДЭК (Пункт выдачи)", callback_data=CB_DELIVERY_TYPE_PICKUP)],
        [InlineKeyboardButton("🟡 Яндекс / Boxberry", callback_data=CB_DELIVERY_TYPE_YANDEX)]
    ]

    # Показываем курьера только если он включен
    if courier_enabled:
        keyboard.insert(1, [InlineKeyboardButton("🚚 Курьер до двери (свой)", callback_data=CB_DELIVERY_TYPE_COURIER)])

    keyboard.append([InlineKeyboardButton("⬅️ Назад в корзину", callback_data=CB_DELIVERY_BACK)])
    return InlineKeyboardMarkup(keyboard)


def get_courier_cities_keyboard(cities: list[Any]) -> InlineKeyboardMarkup:
    """Список городов для выбора пользователем."""
    keyboard = []
    for city in cities:
        btn_text = f"{city['name']} — {city['cost']}₽ ({city['days']} дн.)"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"{CB_DELIVERY_COURIER_CITY}{city['name']}")])

    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data=CB_CHECKOUT)])
    return InlineKeyboardMarkup(keyboard)


# Клавиатура для открытия webapp (генерируется динамически, так как url меняется)
def get_webapp_keyboard(url: str, default_address: Optional[dict[str, Any]] = None) -> InlineKeyboardMarkup:
    """
    Клавиатура для WebApp.
    Если передан default_address, добавляет кнопку быстрого выбора.
    """
    from telegram import WebAppInfo

    keyboard = [
        [InlineKeyboardButton("🗺 Открыть карту и выбрать", web_app=WebAppInfo(url=url))]
    ]

    # Кнопка использования сохраненного адреса
    if default_address:
        # Формируем короткое название: "дом" или "пвз (москва...)"
        name = default_address.get('custom_name') or default_address.get('address_text', 'Адрес')[:20] + '...'
        keyboard.append([
            InlineKeyboardButton(f"🏠 В этот ПВЗ: {name}", callback_data=CB_USE_DEFAULT_ADDRESS)
        ])

    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data=CB_DELIVERY_BACK)])

    return InlineKeyboardMarkup(keyboard)


def get_user_settings_keyboard() -> InlineKeyboardMarkup:
    """Меню настроек с переходом к выходу."""
    keyboard = [
        [InlineKeyboardButton("📍 Мои адреса доставки", callback_data=CB_USER_ADDRESSES)],
        [InlineKeyboardButton("🚪 Выход из аккаунта", callback_data=CB_USER_LOGOUT_MENU)],
        [InlineKeyboardButton("⬅️ Назад в меню", callback_data=CB_USER_SHOW_MAIN_MENU)]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_logout_options_keyboard() -> InlineKeyboardMarkup:
    """Подменю выбора способа выхода."""
    keyboard = [
        [
            InlineKeyboardButton("🚪 Просто выйти", callback_data=CB_USER_LOGOUT_ONLY),
            InlineKeyboardButton("🗑 Удалить данные и выйти", callback_data=CB_USER_DELETE_DATA)
        ],
        [InlineKeyboardButton("⬅️ Отмена", callback_data=CB_USER_SETTINGS)]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_user_addresses_list_keyboard(addresses: List[dict[str, Any]]) -> InlineKeyboardMarkup:
    """Список сохраненных адресов."""
    keyboard = []

    for addr in addresses:
        # Иконка провайдера
        icon = "🟡" if addr['provider'] == 'yandex' else "🟢"
        # Галочка если дефолтный
        check = "✅ " if addr['is_default'] else ""
        # Имя (или часть адреса)
        name = addr.get('custom_name') or addr['address_text'][:20] + "..."

        btn_text = f"{check}{icon} {name}"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"{CB_PREFIX_ADDR_VIEW}{addr['id']}")])

    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data=CB_USER_SETTINGS)])
    return InlineKeyboardMarkup(keyboard)

def get_address_details_keyboard(address_id: int, is_default: bool) -> InlineKeyboardMarkup:
    """Действия с конкретным адресом."""
    keyboard = []

    # Кнопка переименования
    keyboard.append([InlineKeyboardButton("✏️ Переименовать", callback_data=f"{CB_PREFIX_ADDR_RENAME}{address_id}")])

    if not is_default:
        keyboard.append([InlineKeyboardButton("⭐ Сделать основным", callback_data=f"{CB_PREFIX_ADDR_DEF}{address_id}")])

    keyboard.append([InlineKeyboardButton("❌ Удалить", callback_data=f"{CB_PREFIX_ADDR_DEL}{address_id}")])
    keyboard.append([InlineKeyboardButton("⬅️ К списку", callback_data=CB_BACK_TO_ADDR_LIST)])

    return InlineKeyboardMarkup(keyboard)


def get_gift_choice_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора: заказ для себя или в подарок."""
    keyboard = [
        [
            InlineKeyboardButton("👤 Для себя", callback_data=CB_GIFT_FOR_ME),
            InlineKeyboardButton("🎁 В подарок", callback_data=CB_GIFT_AS_PRESENT)
        ],
        [InlineKeyboardButton("⬅️ Назад к выбору доставки", callback_data=CB_DELIVERY_BACK)]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_gift_comment_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для этапа ввода поздравления с кнопкой AI-помощника."""
    keyboard = [
        [InlineKeyboardButton("✨ Помочь написать поздравление?", callback_data=CB_AI_GIFT_HELP)],
        [InlineKeyboardButton("⏭ Пропустить (без текста)", callback_data=CB_GIFT_SKIP)],
        [InlineKeyboardButton("⬅️ Назад", callback_data=CB_GIFT_BACK)],
        [InlineKeyboardButton("🏠 Главное меню", callback_data=CB_GO_TO_MAIN_MENU)]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_ai_gift_options_keyboard(options_count: int) -> InlineKeyboardMarkup:
    """Клавиатура выбора варианта AI-текста с кнопкой повтора."""
    buttons = []
    # Ряд с цифрами 1, 2, 3
    row = [InlineKeyboardButton(f"Вариант {i+1}", callback_data=f"{CB_PREFIX_AI_GIFT_SELECT}{i}") for i in range(options_count)]
    buttons.append(row)

    # Кнопка повтора (новое)
    buttons.append([InlineKeyboardButton("🔄 Попробовать ещё раз (изменить запрос)", callback_data=CB_AI_GIFT_RETRY)])

    # Написать свой текст
    buttons.append([InlineKeyboardButton("✍️ Написать свой текст вручную", callback_data=CB_GIFT_AS_PRESENT)])

    # Отмена
    buttons.append([InlineKeyboardButton("⬅️ Назад к выбору заказа", callback_data=CB_GIFT_BACK)])

    return InlineKeyboardMarkup(buttons)

def get_image_grid_keyboard(product_id: int, img_total: int, category: str) -> InlineKeyboardMarkup:
    """Создает сетку номеров фото."""
    keyboard = []
    row = []
    for i in range(img_total):
        row.append(InlineKeyboardButton(f"{i + 1}", callback_data=f"{CB_PREFIX_PROD_IMG}{product_id}_{i}"))
        if len(row) == 5:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    # Убеждаемся, что кнопка назад четкая
    keyboard.append([InlineKeyboardButton("⬅️ Назад к карточке", callback_data=f"{CB_PREFIX_SELECT_PRODUCT}{product_id}_{category}")])
    return InlineKeyboardMarkup(keyboard)

def get_auth_start_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой запуска регистрации для неавторизованных."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🚀 Начать регистрацию", callback_data=CB_START_REGISTRATION)
    ]])


def get_ai_history_keyboard(current_page: int, total_pages: int) -> InlineKeyboardMarkup:
    """Клавиатура для листания истории."""
    keyboard = []
    nav_row = []

    if total_pages > 1:
        # Кнопка "назад" (на более старые сообщения)
        if current_page > 0:
            nav_row.append(InlineKeyboardButton("⬅️ Раньше", callback_data=f"{CB_AI_HIST_PAGE}{current_page - 1}"))

        # Индикатор
        nav_row.append(InlineKeyboardButton(f"{current_page + 1} / {total_pages}", callback_data="noop"))

        # Кнопка "вперед" (к новым)
        if current_page < total_pages - 1:
            nav_row.append(InlineKeyboardButton("Позже ➡️", callback_data=f"{CB_AI_HIST_PAGE}{current_page + 1}"))

    if nav_row:
        keyboard.append(nav_row)

    # Управление
    keyboard.append([InlineKeyboardButton("💬 Вернуться в чат", callback_data=CB_AI_CHAT_START)])
    keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data=CB_USER_SHOW_MAIN_MENU)])

    return InlineKeyboardMarkup(keyboard)


def get_message_router_keyboard() -> InlineKeyboardMarkup:
    """Меню выбора: AI или Поддержка."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🤖 Спросить AI", callback_data=CB_ROUTER_ASK_AI),
            InlineKeyboardButton("👨‍💼 Поддержка", callback_data=CB_ROUTER_SUPPORT)
        ],
        [InlineKeyboardButton("🏠 Главное меню", callback_data=CB_USER_SHOW_MAIN_MENU)],
        [InlineKeyboardButton("❌ Закрыть", callback_data=CB_CLOSE_GENERIC)]
    ])

def get_support_type_keyboard(last_order_id: int | None = None, has_orders: bool = False) -> InlineKeyboardMarkup:
    """Подменю выбора типа поддержки."""
    keyboard = []

    if last_order_id:
        keyboard.append([InlineKeyboardButton(f"📦 По заказу #{last_order_id}", callback_data=f"{CB_PREFIX_USER_CONTACT_SUPPORT}{last_order_id}")])

    if has_orders:
        # Вместо cb_user_my_orders используем спец. колбэк роутера
        keyboard.append([InlineKeyboardButton("🧾 Выбрать из списка заказов", callback_data=CB_ROUTER_ORDER_LIST)])

    keyboard.append([InlineKeyboardButton("💬 Общая консультация", callback_data=CB_SUPPORT_CONSULTATION)])
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_router")])

    return InlineKeyboardMarkup(keyboard)

def get_pickup_points_keyboard(points: list[Any]) -> InlineKeyboardMarkup:
    """Генерирует список кнопок. Если есть координаты — добавляет кнопку карты."""
    keyboard = []

    for idx, pt in enumerate(points):
        # Ряд 1: кнопка выбора точки
        btn_text = f"📍 {pt['name']} ({pt.get('days', 0)} дн.)"
        row = [InlineKeyboardButton(btn_text, callback_data=f"{CB_PICKUP_POINT_SEL}{idx}")]
        keyboard.append(row)

        # Ряд 2: кнопка "где это?" (только если есть координаты)
        coords = pt.get('coords')
        if coords and ',' in coords:
            # Ссылка на яндекс карты с меткой
            map_url = f"https://yandex.ru/maps/?text={coords.replace(' ', '')}"
            keyboard.append([InlineKeyboardButton("   ∟ 🗺 Посмотреть на карте", url=map_url)])

    keyboard.append([InlineKeyboardButton("⬅️ Назад к выбору доставки", callback_data=CB_CHECKOUT)])
    return InlineKeyboardMarkup(keyboard)


def get_pickup_wizard_keyboard(back_callback: str) -> InlineKeyboardMarkup:
    """Универсальная навигация для мастера добавления: Назад, Отмена, Меню."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⬅️ Назад", callback_data=back_callback),
            InlineKeyboardButton("❌ Отмена", callback_data=CB_ADMIN_PICKUP_MGMT)
        ],
        [InlineKeyboardButton("🏠 Главное меню", callback_data=CB_USER_SHOW_MAIN_MENU)]
    ])

def get_saved_recipes_keyboard(recipes_data: List[dict[str, Any]]) -> InlineKeyboardMarkup:
    """Клавиатура списка сохраненных рецептов."""
    keyboard = []

    for rec in recipes_data:
        p_id = rec['product_id']
        name = rec['product_name']

        # Ряд: [ 📖 название товара ] [ ❌ ]
        keyboard.append([
            InlineKeyboardButton(f"📖 {name}", callback_data=f"{CB_RECIPE_VIEW_SAVED}{p_id}"),
            InlineKeyboardButton("❌", callback_data=f"{CB_RECIPE_DELETE}{p_id}")
        ])

    # Навигация
    keyboard.append([InlineKeyboardButton("⬅️ Назад в Избранное", callback_data=CB_FAVORITES_MENU)])
    keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data=CB_USER_SHOW_MAIN_MENU)])

    return InlineKeyboardMarkup(keyboard)

def get_saved_recipe_view_keyboard(product_id: int) -> InlineKeyboardMarkup:
    """Клавиатура при просмотре текста конкретного сохраненного рецепта."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑 Удалить этот рецепт", callback_data=f"{CB_RECIPE_DELETE}{product_id}")],
        [InlineKeyboardButton("⬅️ К списку рецептов", callback_data=CB_FAV_RECIPES_LIST)],
        [InlineKeyboardButton("🏠 Главное меню", callback_data=CB_USER_SHOW_MAIN_MENU)]
    ])

def get_brewing_methods_keyboard(product_id: int, category: str, is_tea: bool = False) -> InlineKeyboardMarkup:
    """Генерирует список способов заваривания в зависимости от типа напитка."""
    keyboard = []

    if is_tea:
        # Методы для чая
        methods = [
            ("🍵 Проливом (Гунфу)", "gongfu"),
            ("🫖 Настаиванием", "infusion"),
            ("❄️ Cold Brew", "cold_tea")
        ]
    else:
        # Методы для кофе
        methods = [
            ("☕️ Эспрессо", "espresso"),
            ("🌪 Аэропресс", "aeropress"),
            ("⌛️ V60 (Воронка)", "v60"),
            ("🧪 Кемекс", "chemex"),
            ("⚱️ Турка (Джезва)", "cezve"),
            ("🇫🇷 Френч-пресс", "french"),
            ("🧊 Cold Brew", "cold_coffee")
        ]

    # Собираем кнопки по 2 в ряд
    row = []
    for label, code in methods:
        row.append(InlineKeyboardButton(label, callback_data=f"{CB_BREW_METHOD_SELECT}{product_id}_{code}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    # Навигация назад
    keyboard.append([InlineKeyboardButton("⬅️ К описанию товара", callback_data=f"{CB_PREFIX_SELECT_PRODUCT}{product_id}_{category}_details")])

    return InlineKeyboardMarkup(keyboard)


def get_logged_out_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура после выхода: кнопка для возврата к регистрации."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🚀 Войти заново / Зарегистрироваться", callback_data=CB_START_REGISTRATION)
    ]])

def get_start_registration_keyboard() -> InlineKeyboardMarkup:
    """Кнопка перехода от визитки к вводу данных."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🚀 Начать регистрацию", callback_data=CB_START_REGISTRATION)
    ]])

def get_admin_logo_mgmt_keyboard(has_logo: bool) -> InlineKeyboardMarkup:
    """Меню управления приветственной визиткой."""
    keyboard = [
        [InlineKeyboardButton("📝 Изменить текст приветствия", callback_data=CB_ADMIN_WELCOME_TEXT_EDIT)],
        [InlineKeyboardButton("🖼 Изменить медиа (Видео/Фото)", callback_data=CB_ADMIN_LOGO_SET)]
    ]
    if has_logo:
        keyboard.append([InlineKeyboardButton("🗑 Удалить логотип", callback_data=CB_ADMIN_LOGO_DEL)])

    keyboard.append([InlineKeyboardButton("⬅️ Назад в настройки", callback_data=CB_ADMIN_SETTINGS)])
    return InlineKeyboardMarkup(keyboard)

def get_welcome_options_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура приветствия: выбор между просмотром каталога и регистрацией."""
    keyboard = [
        [InlineKeyboardButton("🛍️ Посмотреть каталог", callback_data=CB_USER_START_ORDERING)],
        [InlineKeyboardButton("📝 Начать регистрацию", callback_data=CB_START_REGISTRATION)]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_admin_proxy_mgmt_keyboard(has_proxy_url: bool, is_enabled: bool) -> InlineKeyboardMarkup:
    """Меню управления прокси-сервером с тумблером."""
    keyboard =[]

    # Тумблер показываем только если в базе уже вписан url
    if has_proxy_url:
        toggle_text = "🔴 Выключить Proxy" if is_enabled else "🟢 Включить Proxy"
        keyboard.append([InlineKeyboardButton(toggle_text, callback_data=CB_ADMIN_PROXY_TOGGLE)])

    keyboard.append([InlineKeyboardButton("✏️ Изменить / Установить URL", callback_data=CB_ADMIN_PROXY_SET)])

    if has_proxy_url:
        keyboard.append([InlineKeyboardButton("🗑 Удалить URL", callback_data=CB_ADMIN_PROXY_DEL)])

    keyboard.append([InlineKeyboardButton("⬅️ Назад в настройки", callback_data=CB_ADMIN_SETTINGS)])
    return InlineKeyboardMarkup(keyboard)
