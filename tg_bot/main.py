# Tg_bot/main.py
import asyncio
import json
import logging
import os
import signal
import sys
from pathlib import Path

import asyncpg
import httpx
from dotenv import load_dotenv
from telegram import (
    InlineQueryResultArticle,
    InputTextMessageContent,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    InlineQueryHandler,
    MessageHandler,
    PersistenceInput,
    PicklePersistence,
    filters,
)
from telegram.request import HTTPXRequest


def healthcheck() -> None:
    """Synchronous healthcheck for Docker HEALTHCHECK."""
    import urllib.request

    from tg_bot.infrastructure.secrets_loader import SecretsLoader
    port = SecretsLoader.get_int("BOT_INTERNAL_PORT", 8080)
    try:
        with urllib.request.urlopen(f"http://localhost:{port}/health", timeout=5) as resp:
            if resp.status == 200:
                return
    except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
        logger.warning(f"[databases/kojo/tg_bot/main.py] (RuntimeError, ConnectionError, TimeoutError, OSError): {e}")
    raise SystemExit(1)


project_root = Path(__file__).resolve().parents[1]
sys.path.append(str(project_root))
sys.path.append(str(project_root.parent))  # /app - для импорта services

# Инициализация логирования
from utils.logging_setup import setup_logging

setup_logging(log_level=os.environ.get("LOG_LEVEL", "INFO"), json_format=True)

# Отключаем информационный шум от библиотек запросов
# Logging.getlogger("httpx").setlevel(logging.warning)
# Logging.getlogger("httpcore").setlevel(logging.warning)

logger = logging.getLogger(__name__)

# Отключаем шумные варнинги от ptb
import warnings

from telegram.warnings import PTBUserWarning

warnings.filterwarnings("ignore", category=PTBUserWarning)

# Загрузка переменных окружения
load_dotenv()

# Декораторы и клавиатуры
from typing import Any, Optional

import tg_bot.bot_services.product_sync_service as sync_service
from tg_bot.bot_services.ai_communication_service import AICommunicationService
from tg_bot.bot_services.cart_service import CartService
from tg_bot.bot_services.communication_service import CommunicationService
from tg_bot.bot_services.delivery_service import DeliveryService
from tg_bot.bot_services.favorite_service import FavoriteService
from tg_bot.bot_services.info_service import InfoService
from tg_bot.bot_services.notification_service import NotificationService
from tg_bot.bot_services.order_service import OrderService
from tg_bot.bot_services.payment_service import PaymentService
from tg_bot.bot_services.product_service import ProductService
from tg_bot.bot_services.settings_service import SettingsService
from tg_bot.bot_services.user_address_service import UserAddressService
from tg_bot.bot_services.user_service import UserService
from tg_bot.decorators import auth_guard
from tg_bot.infrastructure.database import DatabaseManager
from tg_bot.handlers.admin_panel import (
    admin_courier_handler,
    admin_logo_handler,
    admin_panel_handlers,
    admin_pickup_conv_handler,
    handle_order_action,
    handle_thread_action,
    panel_start,
    show_communication_center,
    show_order_details,
    show_order_list_by_status,
    show_orders_menu,
    show_thread_view,
    staff_reply_handler,
)
from tg_bot.handlers.ai_chat import (
    handle_ai_history,
    handle_back_to_router,
    handle_router_ask_ai,
    handle_router_support,
    start_ai_chat,
)
from tg_bot.handlers.common import cleanup_previous_menu, handle_stale_callback
from tg_bot.handlers.info import info_conversation
from tg_bot.handlers.order import order_handler
from tg_bot.handlers.registration import (
    handle_approval_callback,
    registration_handler,
    show_main_menu_from_welcome,
    show_staff_main_menu,
    start,
)
from tg_bot.handlers.staff import (
    show_active_orders_shortcut,
    show_my_profile,
    show_stats,
    trigger_manual_sync,
)
from tg_bot.handlers.user_panel import (
    cancel_add_comment,
    cancellation_handler,
    delete_comment_of_order,
    handle_address_action,
    handle_logout_action,
    handle_support_routing,
    order_comment_handler,
    rename_address_handler,
    show_address_details,
    show_logout_options,
    show_my_order_details,
    show_my_orders,
    show_my_orders_for_router,
    show_user_addresses_list,
    show_user_settings,
    show_user_thread_history,
    start_order_rating,
    user_support_handler,
)
from tg_bot.keyboards import (
    CB_ADMIN_BACK_TO_STAFF_MENU,
    CB_ADMIN_COMMUNICATION_CENTER,
    CB_ADMIN_ORDERS_MENU,
    CB_AI_CHAT_HISTORY,
    CB_AI_CHAT_START,
    CB_AI_HIST_PAGE,
    CB_BACK_TO_ADDR_LIST,
    CB_CLOSE_GENERIC,
    CB_PREFIX_ADDR_DEF,
    CB_PREFIX_ADDR_DEL,
    CB_PREFIX_ADDR_VIEW,
    CB_PREFIX_APPROVE,
    CB_PREFIX_DECLINE,
    CB_PREFIX_ORDER_ACTION,
    CB_PREFIX_ORDER_DETAILS,
    CB_PREFIX_ORDERS_BY_STATUS,
    CB_PREFIX_THREAD_ACTION,
    CB_PREFIX_THREAD_DETAILS,
    CB_PREFIX_USER_CONTACT_SUPPORT,
    CB_PREFIX_USER_ORDER_DETAILS,
    CB_ROUTER_ASK_AI,
    CB_ROUTER_ORDER_LIST,
    CB_ROUTER_SUPPORT,
    CB_STAFF_PANEL,
    CB_STAFF_SHOW_PROFILE,
    CB_SUPPORT_CONSULTATION,
    CB_USER_ADDRESSES,
    CB_USER_DELETE_COMMENT_ORDER,
    CB_USER_DELETE_DATA,
    CB_USER_LOGOUT_MENU,
    CB_USER_LOGOUT_ONLY,
    CB_USER_MY_ORDERS,
    CB_USER_RATE_ORDER_START,
    CB_USER_SETTINGS,
    CB_USER_SHOW_MAIN_MENU,
    CB_USER_VIEW_THREAD,
)
from tg_bot.models import UserStatus
from utils.config_pusher import push_config_to_integration


async def init_db_connection(conn: Any) -> Any:
    """
    Настраивает соединение: регистрирует кодеки для JSON/JSONB.
    Теперь asyncpg будет сам делать json.dumps при записи и json.loads при чтении.
    """
    try:
        await conn.set_type_codec(
            'jsonb',
            encoder=json.dumps,
            decoder=json.loads,
            schema='pg_catalog'
        )
        await conn.set_type_codec(
            'json',
            encoder=json.dumps,
            decoder=json.loads,
            schema='pg_catalog'
        )
    except (json.JSONDecodeError, OSError) as e:
        # Иногда кодек уже зарегистрирован, или тип не найден (редко), логируем но не падаем
        logger.warning(f"Ошибка регистрации JSON кодека: {e}")


async def post_init(app: Application) -> Any:
    load_dotenv()
    from tg_bot.infrastructure.secrets_loader import SecretsLoader
    db_url = SecretsLoader.get_required("DATABASE_URL")
    admin_ids_str = SecretsLoader.get("ADMIN_IDS", "")
    app.bot_data['admin_ids'] = [int(i.strip()) for i in admin_ids_str.split(',') if i.strip()]

    # --- Metrics & Health Initialization ---
    from tg_bot.infrastructure.health import get_health_check

    app.bot_data['metrics'] = None
    health = get_health_check()

    # Создание пула
    logger.info("🔌 создание пула соединений с регистрацией json-кодеков...")
    pool = await asyncpg.create_pool(
        db_url,
        min_size=5,
        max_size=20, # Увеличим до 20
        command_timeout=10, # Тайм-аут на выполнение SQL (10 сек)
        init=init_db_connection
    )
    app.bot_data['db_pool'] = pool
    logger.info(f"✅ Пул соединений создан с размером {pool.get_min_size()}-{pool.get_max_size()}.")

    # Регистрируем проверки здоровья
    async def _check_db() -> None:
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
    health.register("postgres", _check_db)
    app.bot_data['health'] = health
    # --- End Metrics & Health ---

    # --- Infrastructure: Event Store, Redis, Idempotency, DLQ ---
    from tg_bot.application.event_handlers.order_event_handler import OrderEventHandler
    from tg_bot.infrastructure.dlq import DeadLetterQueue
    from tg_bot.infrastructure.event_store import EventStore
    from tg_bot.infrastructure.idempotency import IdempotencyStore

    event_store = EventStore(pool)
    app.bot_data['event_store'] = event_store

    redis_client: Any = None
    redis_url = SecretsLoader.get("REDIS_URL", "redis://localhost:6379/0")
    try:
        import redis.asyncio as aioredis
        redis_client = aioredis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        await redis_client.ping()
        logger.info("Redis Connection Established")
    except (aioredis.ConnectionError, aioredis.TimeoutError, OSError) as e:
        logger.warning("Redis unavailable, idempotency/DLQ will use fallback: %s", e)
        redis_client = None
    app.bot_data['redis'] = redis_client

    idempotency_store = IdempotencyStore(redis_client) if redis_client else None
    dlq = DeadLetterQueue(redis_client=redis_client)
    order_event_handler = OrderEventHandler(dlq=dlq)

    dlq.set_handler(lambda item: order_event_handler.handle_event_from_dlq(item))
    app.bot_data['idempotency_store'] = idempotency_store
    app.bot_data['dlq'] = dlq
    app.bot_data['order_event_handler'] = order_event_handler

    if redis_client:
        health.register("redis", lambda: redis_client.ping())

    # DLQ Reprocess Scheduling (every 5 Minutes)
    async def _dlq_reprocess_loop() -> None:
        while True:
            try:
                await asyncio.sleep(300)
                logger.info("[DLQ] Starting Reprocess Cycle...")
                results = await dlq.reprocess(max_items=10)
                if results:
                    logger.info(f"[DLQ] Reprocessed {results} items successfully")
            except asyncio.CancelledError:
                break
            except (RuntimeError, ConnectionError, TimeoutError, OSError) as exc:
                logger.error(f"[DLQ] Reprocess loop error: {exc}")

    dlq_task = asyncio.create_task(_dlq_reprocess_loop())
    app.bot_data["dlq_task"] = dlq_task
    # --- End Infrastructure ---

    # Читаем переменные
    quart_url = SecretsLoader.get_required("QUART_SERVER_URL")
    integration_url = SecretsLoader.get_required("INTEGRATION_SERVER_URL")
    bot_id = SecretsLoader.get_required("BOT_ID_FOR_QUART")

    # Инициализация сервисов
    app.bot_data['user_service'] = UserService(pool)
    app.bot_data['product_service'] = ProductService(pool)
    app.bot_data['order_service'] = OrderService(pool, idempotency_store=idempotency_store)
    app.bot_data['communication_service'] = CommunicationService(pool)

    address_service = UserAddressService(pool)
    await address_service.init_table() # Создаем таблицу, если нет
    app.bot_data['address_service'] = address_service

    # 1. сначала favorites
    fav_service = FavoriteService(pool)
    await fav_service.init_table()
    app.bot_data['favorite_service'] = fav_service

    # 2. потом notificationservice
    notif_service = NotificationService(app)
    app.bot_data['notification_service'] = notif_service

    # Paymentservice теперь использует integration_url
    app.bot_data['payment_service'] = PaymentService(
        quart_url=integration_url, # Используем новый адрес
        bot_id=bot_id,
        idempotency_store=idempotency_store,
    )

    app.bot_data['settings_service'] = SettingsService(pool)
    db_manager = DatabaseManager(pool)
    app.bot_data['db_manager'] = db_manager
    app.bot_data['cart_service'] = CartService(pool, db_manager=db_manager)
    app.bot_data['info_service'] = InfoService(pool)

    # Вставить после инициализации info_service
    # Create Gatewayclient For AI Communication With Circuit Breaker + HMAC
    from services.gateway.client import GatewayClient
    ai_gateway = GatewayClient(base_url=quart_url)

    app.bot_data['ai_comm_service'] = AICommunicationService(
        quart_url=quart_url,
        bot_id=bot_id,
        gateway=ai_gateway,
    )
    logger.info("✅ ai communication service инициализирован.")

    # Deliveryservice теперь использует integration_url
    app.bot_data['delivery_service'] = DeliveryService(
        quart_url=integration_url, # Используем новый адрес
        bot_id=bot_id
    )

    # Настройка прокси (best-practice): если в конфиге use_proxy=true и не задан tg_proxy_url,
    # Делаем асинхронный выбор прокси (health-checked) до сетевых операций (sync_products, push_config и т.д.)
    try:
        config_path_local = Path("config/config.json")
        use_proxy_cfg = False
        if config_path_local.exists():
            try:
                use_proxy_cfg = json.loads(config_path_local.read_text("utf-8")).get("use_proxy", False)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"[post_init] не удалось прочитать config/config.json для проверки use_proxy: {e}")

        if use_proxy_cfg and not os.environ.get("TG_PROXY_URL"):
            try:
                from services.proxy_adapter import get_proxy_adapter
                adapter = get_proxy_adapter(bot_id)
                selected = await adapter.async_set_proxy()
                if selected:
                    logger.info(f"🌐 [post_init PROXY] Установлен рабочий прокси: {selected.url}")
                else:
                    logger.info("🌐 [post_init proxy] прокси не выбран — работаем напрямую.")
            except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
                logger.warning(f"[post_init] Ошибка при установке прокси: {e}")
    except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
        logger.warning(f"[post_init] Ошибка проверки/установки прокси: {e}")

    # Синхронизация и рассылка

    # 3. синхронизация продуктов (загрузка из файлов в бд)
    await sync_service.sync_products(pool)
    logger.info("🔄 синхронизация продуктов завершена.")

    # 4. запуск проверки: появились ли товары, которые ждали люди?
    # Это происходит сразу после обновления базы.
    await notif_service.process_restock_notifications()

    # Отправляем конфиг
    await push_config_to_integration(pool)
    logger.info("📤 конфигурация отправлена в интеграционный сервис.")

    app.bot_data['welcome_message'] = os.environ.get("WELCOME_MESSAGE", "Добро пожаловать!")
    app.bot_data['admin_chat_id'] = SecretsLoader.get_required("ADMIN_CHAT_ID")

    # Настройка telegram-алертинга (уведомления об error/critical)
    from tg_bot.infrastructure.alerting import setup_alerting
    setup_alerting(app)

    # Сохраняем urls в bot_data на всякий случай
    app.bot_data['quart_url'] = quart_url
    app.bot_data['bot_id_for_quart'] = bot_id
    app.bot_data['integration_url'] = integration_url
    logger.info("✅ приложение инициализировано и готово к работе.")


async def handle_unregistered_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """Глобальный диспетчер с зачисткой iOS-панелей по правилу 1 экрана."""
    if not update.message or not update.message.text:
        return
    user_id = update.effective_user.id  # type: ignore[union-attr]

    if not await _check_user_access(user_id, update, context):
        return

    if context.user_data.get('is_ai_chat_mode'):  # type: ignore[union-attr]
        ai_service = context.bot_data['ai_comm_service']
        await ai_service.handle_ai_workflow(update, context)
        return

    # Логика роутера
    user_msg = update.message.text
    context.user_data['pending_message_text'] = user_msg  # type: ignore[index]

    from tg_bot.keyboards import get_message_router_keyboard
    text = (
        f"❓ <b>Ваше сообщение получено:</b>\n\n"
        f"<i>«{user_msg[:100]}{'...' if len(user_msg) > 100 else ''}»</i>\n\n"
        f"Кому вы хотите адресовать этот вопрос?"
    )

    # [правило ios] 1. сначала отправляем новое сообщение
    msg = await context.bot.send_message(
        chat_id=user_id,
        text=text,
        reply_markup=get_message_router_keyboard(),
        parse_mode='HTML'
    )
    new_id = msg.message_id

    # 2. удаляем текст, который ввел пользователь (чистота чата)
    try:
        await update.message.delete()
    except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
                logger.warning(f"[databases/kojo/tg_bot/main.py] (RuntimeError, ConnectionError, TimeoutError, OSError): {e}")

    # [правило ios] 3. очищаем старые меню до перезаписи якоря в бд!
    await cleanup_previous_menu(context, user_id, exclude_id=new_id)

    # [правило ios] 4. только после успешной очистки обновляем якорь на новый
    context.user_data['last_global_menu_id'] = new_id  # type: ignore[index]
    await context.bot_data['user_service'].save_registration_message_id(user_id, new_id)

    logger.info(f"🚦 Router UI: Prompt sent (ID: {new_id}), old UI cleaned.")


# Вспомогательные функции
async def _check_user_access(user_id: int, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Проверяет, одобрен ли пользователь."""
    user_service: UserService = context.bot_data['user_service']
    user_db = await user_service.get_user(user_id)

    if not user_db or user_db.status != UserStatus.APPROVED:
        logger.info(f"[Access] Пользователь {user_id} не одобрен. Отправка приглашения.")
        await update.message.reply_text("Здравствуйте! Чтобы начать работу с ботом, пожалуйста, отправьте команду /start.")  # type: ignore[union-attr]
        return False
    return True


async def post_shutdown(app: Application) -> Any:
    """Graceful shutdown: закрываем внешние соединения."""
    logger.info("🛑 Shutdown Signal Received, Cleaning Up...")

    # 1. Gateway Clients
    try:
        from services.gateway.client import clear_gateway_clients
        await clear_gateway_clients()
        logger.info("✅ Gateway Clients Closed")
    except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
        logger.warning(f"⚠️ Error closing gateway clients: {e}")

    # 2. proxy pools (если используются)
    try:
        from services.proxy_pool import clear_all_pools
        clear_all_pools()
        logger.info("✅ Proxy Pools Cleared")
    except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
        logger.warning(f"⚠️ Error clearing proxy pools: {e}")

    # 3. сервисы из bot_data
    service_keys = [
        'user_service', 'product_service', 'order_service',
        'payment_service', 'settings_service', 'communication_service',
        'cart_service', 'info_service', 'delivery_service'
    ]
    for key in service_keys:
        if key in app.bot_data:
            del app.bot_data[key]
            logger.info(f"Сервис '{key}' удален из bot_data.")

    # 4. DB Pool
    pool: asyncpg.Pool = app.bot_data.pop('db_pool', None)
    if pool:
        await pool.close()
        logger.info("✅ DB Pool Closed")

    logger.info("✅ Graceful Shutdown Complete")


async def log_all_webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """
    Глобальный логгер для отладки WebApp.
    Ловит ВСЕ данные от веб-приложений, независимо от состояния диалога.
    """
    if update.effective_message.web_app_data:  # type: ignore[union-attr]
        raw_data = update.effective_message.web_app_data.data  # type: ignore[union-attr]
        user_id = update.effective_user.id  # type: ignore[union-attr]
        logger.info(f"🚨 [GLOBAL WEBAPP LOG] Получены данные от user {user_id}:")
        logger.info(f"📝 PAYLOAD: {raw_data}")

        # Для теста можно даже ответить пользователю, чтобы он понял, что бот жив
        # Await update.effective_message.reply_text(f"debug: данные получены!\n{raw_data[:100]}...")


async def inline_query_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """
    Профессиональный Inline-поиск товаров.
    Гарантирует стабильность ссылок за счет сохранения префикса 'p'.
    """
    query = update.inline_query.query.strip()  # type: ignore[union-attr]
    if not query:
        return

    product_service: ProductService = context.bot_data['product_service']
    results = await product_service.search_products(query)

    inline_results = []
    # Получаем username бота один раз для всех ссылок
    bot_obj = await context.bot.get_me()
    bot_username = bot_obj.username

    # Берем первые 15 результатов (баланс между скоростью и выбором)
    for p in results[:
        15]:
        price = f"{p.variants[0].price}₽" if p.variants else ""
        desc = p.short_description or ""

        # [критично] сохраняем оригинальный префикс 'p', чтобы не сломать логику в registration.py
        bot_url = f"https://t.me/{bot_username}?start=p{p.id}"

        # Формируем сообщение, которое будет отправлено в чат
        content_text = (
            f"☕️ <b>{p.name.upper()}</b>\n\n"
            f"<i>{desc}</i>\n\n"
            f"💰 Цена: <b>{price}</b>\n"
            f"<a href='{bot_url}'>👉 Посмотреть в магазине</a>"
        )

        inline_results.append(
            InlineQueryResultArticle(
                id=f"in_{p.id}", # Уникальный ID результата
                title=f"{p.name} — {price}",
                description=desc[:100],
                input_message_content=InputTextMessageContent(
                    content_text,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=False # Оставляем возможность предпросмотра ссылки
                )
            )
        )

    logger.info(f"✨ Inline Search: выдано {len(inline_results)} результатов по запросу '{query}'")
    if update.inline_query:
        await update.inline_query.answer(inline_results, cache_time=300)


async def handle_orders_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
    """
    Единый роутер для /orders:
    - персонал -> список активных заказов
    - пользователь -> мои заказы
    """
    user_service: UserService = context.bot_data['user_service']
    admin_ids = context.bot_data.get('admin_ids', [])
    user_id = update.effective_user.id if update.effective_user else None

    if not user_id:
        return

    user_db = await user_service.get_user(user_id)
    if user_service.has_staff_privileges(user_db, admin_ids):
        return await show_active_orders_shortcut(update, context)
    return await show_my_orders(update, context)


async def _graceful_shutdown(
    app: Application,
    health_runner: Any,
) -> None:
    """Execute graceful shutdown per manifest §3.1."""
    logger.info("Graceful Shutdown Started")

    # 0. Cancel DLQ Reprocess Task
    dlq_task = app.bot_data.get("dlq_task")
    if dlq_task:
        dlq_task.cancel()
        try:
            await dlq_task
        except asyncio.CancelledError as e:
            logger.debug(f"[databases/kojo/tg_bot/main.py] CancelledError (expected): {e}")
        logger.info("DLQ Reprocess Task Cancelled")

    # 1. Flush Event Store WAL (manifest §3.1)
    event_store = app.bot_data.get('event_store')
    if event_store:
        try:
            await event_store.flush()
            logger.info("Event Store WAL Flushed")
        except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
            logger.error("Failed to flush event store WAL: %s", e)

    # 2. Drain DLQ (manifest §3.1)
    dlq = app.bot_data.get('dlq')
    if dlq:
        try:
            await dlq.drain(timeout=5.0)
            logger.info("DLQ Drained")
        except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
            logger.error("DLQ drain error: %s", e)

    # 3. Stop Accepting New Updates
    if app.updater and getattr(app.updater, 'running', False):
        await app.updater.stop()
        logger.info("Updater Stopped")

    # 4. Give Active Handlers Time To Finish
    await asyncio.sleep(2)

    # 5. Close DB Pool
    db_pool = app.bot_data.get("db_pool")
    if db_pool:
        await db_pool.close()
        logger.info("DB Pool Closed")

    # 6. Close Gateway Client
    gateway = app.bot_data.get("gateway_client")
    if gateway:
        await gateway.close()
        logger.info("Gateway Client Closed")

    # 7. Close Redis If Present
    redis = app.bot_data.get("redis")
    if redis:
        await redis.close()
        logger.info("Redis Closed")

    # 8. Stop Health Server
    if health_runner:
        await health_runner.cleanup()
        logger.info("Health Server Stopped")

    # 9. Finalize PTB Application
    await app.stop()
    await app.shutdown()
    logger.info("Graceful Shutdown Complete")


async def main() -> None:
    # 1. загружаем переменные окружения
    load_dotenv()
    from tg_bot.infrastructure.secrets_loader import SecretsLoader
    TOKEN = SecretsLoader.get_required("BOT_TOKEN")

    # Сброс персистентности (если нужно)
    persistence_path = Path(os.getenv("BOT_PERSISTENCE_PATH", "/app/data/bot_persistence.pickle"))
    if os.environ.get("RESET_PERSISTENCE", "false").lower() == "true":
        if persistence_path.exists():
            try:
                persistence_path.unlink()
                logger.warning("🗑️ файл bot_persistence.pickle был удален по запросу (reset_persistence).")
            except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
                logger.error(f"Не удалось удалить файл персистентности: {e}")

    persistence = PicklePersistence(
        filepath=str(persistence_path),
        update_interval=60,
        store_data=PersistenceInput(bot_data=False, user_data=True, chat_data=True, callback_data=True)
    )

    # Логика прокси
    # 1. читаем флаг из конфига
    use_proxy_flag = False
    config_path = Path("config/config.json") # Путь относительно корня контейнера

    try:
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)
                use_proxy_flag = config_data.get("use_proxy", False)
                logger.info(f"📖 Config read: use_proxy={use_proxy_flag}")
        else:
            logger.warning(f"⚠️ Config file not found at {config_path}")
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"❌ Ошибка чтения config.json: {e}")

    # 2. читаем url из env
    env_proxy_url = os.environ.get("TG_PROXY_URL")
    active_proxy_url = None

    # 3. принимаем решение
    if use_proxy_flag:
        if env_proxy_url:
            active_proxy_url = env_proxy_url
            logger.info(f"🌐 [PROXY START] Бот запускается через прокси: {active_proxy_url}")
        else:
            # Попытка надежного выбора прокси (health-checked) через асинхронный адаптер.
            try:
                from services.proxy_adapter import get_proxy_adapter
                bot_id_for_pool = SecretsLoader.get("BOT_ID_FOR_QUART", "default")
                adapter = get_proxy_adapter(bot_id_for_pool)
                try:
                    selected = await adapter.async_set_proxy()
                    if selected:
                        active_proxy_url = selected.url
                        logger.info(f"🌐 [PROXY START] Выбран прокси из пула: {active_proxy_url}")
                    else:
                        logger.warning("⚠️ use_proxy=true, но пул не дал доступных прокси. иду напрямую.")
                except (httpx.HTTPError, ConnectionError, TimeoutError) as e:
                    logger.warning(f"⚠️ Ошибка при выборке прокси (startup): {e}. Попробую fallback.")
                    try:
                        adapter.set_proxy_env()  # type: ignore[attr-defined]
                        active_proxy_url = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')
                        if active_proxy_url:
                            logger.info(f"🌐 [PROXY START] (fallback) Прокси установлен: {active_proxy_url}")
                    except (RuntimeError, ConnectionError, TimeoutError, OSError):
                        logger.warning("⚠️ fallback set_proxy_env не удался. иду напрямую.")
            except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
                logger.warning(f"⚠️ Ошибка инициализации ProxyAdapter: {e}. Иду напрямую.")
    else:
        logger.info("🌐 [direct start] прокси выключен в конфиге (use_proxy: false).")

    # Настраиваем глобальные таймауты (180 сек для тяжелых фото)
    t_request = HTTPXRequest(
        connection_pool_size=20,
        connect_timeout=30.0,
        read_timeout=180.0,
        write_timeout=180.0
    )

    # Создаем билдер
    Application.builder().token(TOKEN).request(t_request).persistence(persistence)

    # Если прокси активен, добавляем его в билдер
    if active_proxy_url:
        logger.info(f"🌐 [PROXY START] Бот запускается через прокси: {active_proxy_url}")
        # Самый надежный способ для httpx:
        # Устанавливаем переменную только для https (telegram api),
        # Чтобы не сломать локальные http запросы к сервисам
        os.environ['HTTPS_PROXY'] = active_proxy_url
    else:
        # Если прокси выключен, на всякий случай чистим переменную, чтобы не подхватилась из системы
        if 'HTTPS_PROXY' in os.environ:
            del os.environ['HTTPS_PROXY']
        logger.info("🌐 [direct start] прокси выключен (используем прямое соединение).")

    # Инициализируем request с прокси (если задан)
    t_request_kwargs = dict(
        connection_pool_size=20,
        connect_timeout=30.0,
        read_timeout=180.0,
        write_timeout=180.0
    )
    if active_proxy_url:
        t_request_kwargs['proxy'] = active_proxy_url  # type: ignore[assignment]
        logger.info(f"🌐 [HTTPXRequest] Прокси передан напрямую: {active_proxy_url}")
    t_request = HTTPXRequest(**t_request_kwargs)  # type: ignore[arg-type]

    # Билдер без выдуманных методов .proxy_url()
    application = (
        Application.builder()
        .token(TOKEN)
        .request(t_request)
        .persistence(persistence)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    # Middleware Support Via Process_update Wrapping (PTB 20.x Lacks Add_middleware)
    from tg_bot.infrastructure.observability_middleware import ObservabilityMiddleware
    from tg_bot.rate_limit_middleware import app_middleware

    _orig_process_update = application.process_update

    async def _run_middleware_chain(update: Update) -> None:
        ctx = application.context_types.context.from_update(update, application)
        await ctx.refresh_data()

        async def _dispatch() -> None:
            await _orig_process_update(update)

        async def _rate_limit(_update: object, _context: object) -> None:
            await app_middleware(update, ctx, _dispatch)

        await ObservabilityMiddleware()(update, ctx, _rate_limit)

    application.process_update = _run_middleware_chain  # type: ignore[method-assign,assignment]

    # Ловим именно служебные сообщения с данными webapp (для отладки)
    from telegram.ext import TypeHandler
    # Регистрация хендлеров (порядок критичен)
    # 1. служебные (group -1)
    async def debug_log_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
        pass
        # Logger.info(f"📨 Update: {update.update_id} | User: {user} | Data: {data}")

    application.add_handler(TypeHandler(Update, debug_log_update), group=-1)
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, log_all_webapp_data), group=-1)

    # 2. стейт-диалоги (conversationhandlers)
    application.add_handler(admin_logo_handler)
    application.add_handler(admin_pickup_conv_handler)
    application.add_handler(admin_courier_handler)
    application.add_handler(rename_address_handler)
    application.add_handler(registration_handler)
    application.add_handler(order_handler)
    application.add_handler(staff_reply_handler)
    application.add_handler(info_conversation)
    application.add_handler(user_support_handler)
    application.add_handler(cancellation_handler)
    application.add_handler(order_comment_handler)

    # 3. роутинг и ai (кнопки выбора пути)
    application.add_handler(CallbackQueryHandler(start_ai_chat, pattern=f"^{CB_AI_CHAT_START}$"))
    application.add_handler(CallbackQueryHandler(handle_ai_history, pattern=f"^{CB_AI_CHAT_HISTORY}$|^{CB_AI_HIST_PAGE}"))
    application.add_handler(CallbackQueryHandler(handle_router_ask_ai, pattern=f"^{CB_ROUTER_ASK_AI}$"))
    application.add_handler(CallbackQueryHandler(handle_router_support, pattern=f"^{CB_ROUTER_SUPPORT}$"))
    application.add_handler(CallbackQueryHandler(handle_back_to_router, pattern="^back_to_router$"))
    application.add_handler(CallbackQueryHandler(show_my_orders_for_router, pattern=f"^{CB_ROUTER_ORDER_LIST}$"))

    application.add_handler(CallbackQueryHandler(handle_support_routing, pattern=f"^{CB_SUPPORT_CONSULTATION}$|^{CB_PREFIX_USER_CONTACT_SUPPORT}"))

    # 4. админ-панель и персонал
    application.add_handler(CallbackQueryHandler(auth_guard(staff_only=True)(panel_start), pattern=f"^{CB_STAFF_PANEL}$"))
    application.add_handler(CallbackQueryHandler(show_my_profile, pattern=f"^{CB_STAFF_SHOW_PROFILE}$"))
    application.add_handler(CallbackQueryHandler(auth_guard(staff_only=True)(show_staff_main_menu), pattern=f"^{CB_ADMIN_BACK_TO_STAFF_MENU}$"))

    for handler in admin_panel_handlers:
        application.add_handler(handler)

    application.add_handler(CallbackQueryHandler(show_orders_menu, pattern=f"^{CB_ADMIN_ORDERS_MENU}$"))
    application.add_handler(CallbackQueryHandler(show_order_list_by_status, pattern=f"^{CB_PREFIX_ORDERS_BY_STATUS}"))
    application.add_handler(CallbackQueryHandler(show_order_details, pattern=f"^{CB_PREFIX_ORDER_DETAILS}"))
    application.add_handler(CallbackQueryHandler(handle_order_action, pattern=f"^{CB_PREFIX_ORDER_ACTION}"))

    application.add_handler(CallbackQueryHandler(show_communication_center, pattern=f"^{CB_ADMIN_COMMUNICATION_CENTER}$"))
    application.add_handler(CallbackQueryHandler(show_thread_view, pattern=f"^{CB_PREFIX_THREAD_DETAILS}"))
    application.add_handler(CallbackQueryHandler(handle_thread_action, pattern=f"^{CB_PREFIX_THREAD_ACTION}"))


    # 5. пользовательский интерфейс
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", show_main_menu_from_welcome))
    application.add_handler(CommandHandler("orders", handle_orders_command))

    application.add_handler(CallbackQueryHandler(show_my_orders, pattern=f"^{CB_USER_MY_ORDERS}$"))
    application.add_handler(CallbackQueryHandler(show_my_order_details, pattern=f"^{CB_PREFIX_USER_ORDER_DETAILS}"))
    application.add_handler(CallbackQueryHandler(show_main_menu_from_welcome, pattern=f"^{CB_USER_SHOW_MAIN_MENU}$"))
    application.add_handler(CallbackQueryHandler(show_user_thread_history, pattern=f"^{CB_USER_VIEW_THREAD}"))

    application.add_handler(CallbackQueryHandler(handle_approval_callback, pattern=f"^{CB_PREFIX_APPROVE}|^{CB_PREFIX_DECLINE}"))

    application.add_handler(CallbackQueryHandler(show_user_settings, pattern=f"^{CB_USER_SETTINGS}$"))
    application.add_handler(CallbackQueryHandler(show_user_addresses_list, pattern=f"^{CB_USER_ADDRESSES}$|^{CB_BACK_TO_ADDR_LIST}$"))
    application.add_handler(CallbackQueryHandler(show_address_details, pattern=f"^{CB_PREFIX_ADDR_VIEW}"))
    application.add_handler(CallbackQueryHandler(handle_address_action, pattern=f"^{CB_PREFIX_ADDR_DEL}|^{CB_PREFIX_ADDR_DEF}"))

    application.add_handler(CallbackQueryHandler(delete_comment_of_order, pattern=f"^{CB_USER_DELETE_COMMENT_ORDER}"))
    application.add_handler(CallbackQueryHandler(start_order_rating, pattern=f"^{CB_USER_RATE_ORDER_START}"))

    application.add_handler(CallbackQueryHandler(show_logout_options, pattern=f"^{CB_USER_LOGOUT_MENU}$"))
    application.add_handler(CallbackQueryHandler(handle_logout_action, pattern=f"^{CB_USER_LOGOUT_ONLY}$|^{CB_USER_DELETE_DATA}$"))

    # 6. общие команды
    application.add_handler(CommandHandler("stats", auth_guard(staff_only=True)(show_stats)))
    application.add_handler(CommandHandler("sync", trigger_manual_sync))

    application.add_handler(CallbackQueryHandler(lambda u, c: u.callback_query.message.delete(), pattern=f"^{CB_CLOSE_GENERIC}$"))  # type: ignore[union-attr]
    application.add_handler(CallbackQueryHandler(cancel_add_comment, pattern="^cancel_add_comment$"))
    application.add_handler(InlineQueryHandler(inline_query_search))

    # 7. глобальный текст
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unregistered_messages))

    # 8. Janitor
    application.add_handler(CallbackQueryHandler(handle_stale_callback, pattern=".*"))

    # Фоновый репорт метрик каждые 60 секунд
    async def _metrics_reporter() -> None:
        while True:
            await asyncio.sleep(60)
            metrics = application.bot_data.get('metrics')
            if metrics:
                report = metrics.report()
                logger.info(f"📊 Metrics: {report}")
            health = application.bot_data.get('health')
            if health:
                status = await health.run()
                if status['status'] != 'ok':
                    logger.warning(f"🏥 Health: {status}")

    # Запускаем репортер при старте
    asyncio.create_task(_metrics_reporter())

    # Запуск
    from tg_bot.infrastructure.secrets_loader import SecretsLoader
    internal_port = SecretsLoader.get_int("BOT_INTERNAL_PORT", 8080)
    public_url = SecretsLoader.get("WEBHOOK_PUBLIC_URL")
    secret_token = SecretsLoader.get("WEBHOOK_SECRET_TOKEN")
    logger.info("[DEBUG] WEBHOOK_PUBLIC_URL configured=%s len=%s", bool(public_url), len(public_url or ""))

    if not public_url:
        logger.warning("⚠️ webhook_public_url не задан — бот работает в listener mode без публичного url")

    logger.info(f"🚀 Запуск бота (Webhook Mode). Port: {internal_port}")

    # --- Graceful Shutdown Setup ---
    _shutdown_event = asyncio.Event()

    def _signal_handler(sig: signal.Signals) -> None:
        logger.info(f"Received signal {sig.name}, initiating graceful shutdown...")
        _shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: _signal_handler(s))  # type: ignore[misc]

    # --- Start Services ---
    await application.initialize()
    await post_init(application)
    await application.start()

    # Запускаем aiohttp сервер для webhook listener mode
    from aiohttp import web

    _webhook_runner: Optional[web.AppRunner] = None
    _webhook_site: Optional[web.TCPSite] = None

    async def handle_webhook(request: web.Request) -> web.Response:
        if secret_token:
            received_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
            if received_token != secret_token:
                logger.warning("Invalid Secret Token Received")
                return web.Response(status=403)
        try:
            data = await request.json()
            update = Update.de_json(data, application.bot)
            await application.update_queue.put(update)
            return web.Response(text="OK")
        except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
            logger.error(f"Error processing webhook: {e}")
            return web.Response(status=500)

    from tg_bot.infrastructure.health_server import create_health_app

    app = create_health_app(
        db_pool=application.bot_data.get("db_pool"),
        redis=application.bot_data.get("redis")
    )
    app.router.add_post("/", handle_webhook)

    _webhook_runner = web.AppRunner(app)
    await _webhook_runner.setup()
    _webhook_site = web.TCPSite(_webhook_runner, "0.0.0.0", internal_port)
    await _webhook_site.start()

    logger.info(f"Bot started in webhook listener mode on port {internal_port} (waiting for integration-service)")

    # --- Wait For Shutdown Signal ---
    await _shutdown_event.wait()

    # --- Execute Shutdown ---
    if _webhook_site:
        await _webhook_site.stop()
    if _webhook_runner:
        await _webhook_runner.cleanup()
    await _graceful_shutdown(application, _webhook_runner)


if __name__ == "__main__":
    asyncio.run(main())
