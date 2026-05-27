from __future__ import annotations

# Tg_bot/bot_services/ai_communication_service.py
import asyncio
import logging
import os
import re
from typing import Any, Optional, cast

import httpx
import telegram
from dateutil.parser import parse as parse_date
from telegram import Update, constants
from telegram.ext import ContextTypes

from services.gateway.circuit_breaker import CircuitOpenError
from tg_bot.handlers.common import cleanup_previous_menu
from tg_bot.infrastructure.html_pipeline import prepare_html_for_telegram
from tg_bot.keyboards import get_ai_chat_keyboard

logger = logging.getLogger(__name__)


def sanitize_for_llm_prompt(text: str, max_length: int = 2000) -> str:
    """Sanitize user input for LLM prompt. Blocks dangerous content."""
    if not text:
        return ""

    # Block Script Tags And Event Handlers
    text = re.sub(r'<script[^>]*>.*?</script>', '[BLOCKED]', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'on\w+\s*=', '[BLOCKED]', text, flags=re.IGNORECASE)

    # Truncate If Too Long (without Ellipsis)
    if len(text) > max_length:
        text = text[:max_length]

    return text.strip()


class ThinkingAnimator:
    """Анимирует сообщение (Печатает...) и поддерживает статус в шапке чата."""
    def __init__(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int, initial_message: telegram.Message) -> None:
        self.context = context
        self.chat_id = chat_id
        self.message = initial_message
        self.is_running = True
        self.task: Optional[asyncio.Task[Any]] = None

    async def start(self) -> None:
        self.task = asyncio.create_task(self._animate_loop())

    async def stop(self) -> None:
        self.is_running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError as e:
                logger.debug(f"[databases/kojo/tg_bot/bot_services/ai_communication_service.py] CancelledError (expected): {e}")

    async def _animate_loop(self) -> Any:
        dot_count = 1
        try:
            while self.is_running:
                await self.context.bot.send_chat_action(chat_id=self.chat_id, action=constants.ChatAction.TYPING)
                text = f"Печатает{'.' * dot_count} ☕️"
                try:
                    await self.context.bot.edit_message_text(
                        chat_id=self.chat_id, message_id=self.message.message_id, text=text
                    )
                except telegram.error.BadRequest as e:
                    logger.debug(f"[databases/kojo/tg_bot/bot_services/ai_communication_service.py] BadRequest (expected): {e}")
                dot_count = (dot_count % 3) + 1
                await asyncio.sleep(1.5)
        except asyncio.CancelledError as e:
            logger.debug(f"[databases/kojo/tg_bot/bot_services/ai_communication_service.py] CancelledError (expected): {e}")

class AICommunicationService:
    def __init__(self, quart_url: str, bot_id: str, gateway: Any = None) -> None:
        self.quart_url = quart_url # Это URL малого сервера (Remote)
        self.bot_id = bot_id
        self.timeout = httpx.Timeout(300.0, connect=10.0)
        self._llm_client = None
        self._http_middleware = None
        self._gateway = gateway

    async def get_ai_answer(self, user_id: int, topic: str, nickname: str) -> dict[str, Any]:
        """Получает ответ от LLM. Сначала пробует LLM-клиент, потом fallback через middleware."""
        logger.info(f"[AI-Service] Запрос ответа для {user_id}")

        # 1. пробуем через llm-клиент
        if self._llm_client:
            try:
                # Sanitize User Input Before Sending To LLM
                safe_topic = sanitize_for_llm_prompt(topic, max_length=2000)
                result = await self._llm_client.chat_json(safe_topic, user_id=user_id, nickname=nickname)
                if result is not None:
                    return result
            except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
                logger.warning(f"LLM client failed: {e}, falling back to middleware")

        # 2. fallback через http middleware
        return await self._fallback_to_quart(user_id, topic, nickname)

    async def _fallback_to_quart(self, user_id: int, topic: str, nickname: str) -> dict[str, Any]:
        """Fallback к Quart серверу через HTTP middleware."""
        logger.info(f"[AI-Service] Fallback to Quart for {user_id}")

        data = {
            "bot_id": self.bot_id,
            "user_id": str(user_id),
            "topic": topic,
            "user_nickname": nickname
        }

        # Primary: Gatewayclient With Circuit Breaker + HMAC
        if self._gateway:
            try:
                response = await self._gateway._request("POST", "", json=data)
                if response.status_code == 202:
                    return {"status": "indexing", "answer": "⚙️ База знаний обновляется..."}
                return cast(dict[str, Any], response.json())
            except CircuitOpenError:
                logger.warning("Circuit Open For Quart, Falling Back To Middleware")
            except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
                logger.error(f"Gateway Quart request failed: {e}, falling back to middleware")

        # Fallback: Legacy Http Middleware
        if self._http_middleware:
            try:
                response = await self._http_middleware.post(self.quart_url, json=data)
                if response.status_code == 202:
                    return {"status": "indexing", "answer": "⚙️ База знаний обновляется..."}
                response.raise_for_status()
                return response.json()
            except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
                logger.error(f"Fallback to Quart failed: {e}")
                return {"answer": "⚠️ Ошибка при обращении к серверу."}

        return {"answer": "⚠️ Сервис временно недоступен."}

    async def get_semantic_retrieval(self, query: str) -> list[str]:
        """Получает семантический контекст через HTTP middleware и извлекает названия товаров."""
        # Primary: Gatewayclient With Circuit Breaker + HMAC
        if self._gateway:
            try:
                response = await self._gateway._request(
                    "POST", "/semantic", json={"query": query}
                )
                data = cast(dict[str, Any], response.json())
                context = data.get("context", [])

                product_names = []
                for chunk in context:
                    match = re.search(r"###\s*Товар:\s*(.*?)\s*###", chunk, re.IGNORECASE)
                    if match:
                        product_names.append(match.group(1).strip())

                return product_names if product_names else context  # type: ignore[no-any-return]
            except CircuitOpenError:
                logger.warning("Circuit Open For Semantic Retrieval, Falling Back To Middleware")
            except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
                logger.error(f"Gateway semantic retrieval failed: {e}, falling back to middleware")

        # Fallback: Legacy Http Middleware
        if self._http_middleware:
            try:
                response = await self._http_middleware.post(
                    f"{self.quart_url}/semantic",
                    json={"query": query}
                )
                response.raise_for_status()
                data = cast(dict[str, Any], response.json())
                context = data.get("context", [])

                product_names = []
                for chunk in context:
                    match = re.search(r"###\s*Товар:\s*(.*?)\s*###", chunk, re.IGNORECASE)
                    if match:
                        product_names.append(match.group(1).strip())

                return product_names if product_names else context
            except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
                logger.error(f"Semantic retrieval failed: {e}")
                return []

        return []


    async def handle_ai_workflow(self, update: Update, context: ContextTypes.DEFAULT_TYPE, override_topic: Optional[str] = None) -> Any:
        """
        Логика 'одного окна' для AI.
        Защита iOS: Отправляем плашку ДО удаления предыдущего меню.
        """
        if not update.effective_user:
            return
        user_id = update.effective_user.id
        if not update.effective_chat:
            return
        chat_id = update.effective_chat.id
        user_service = context.bot_data['user_service']
        user_data = context.user_data
        if user_data is None:
            user_data = {}
        user_text = override_topic if override_topic else (update.message.text if update.message else None)
        if not user_text:
            return

        # 1. определяем, работаем ли мы через редактирование (callback) или через новое сообщение (text)
        query = update.callback_query
        placeholder_text = "🔍 Минутку, думаю..."

        if query:
            # Сценарий а: вызов из кнопки роутера — редактируем текущее сообщение
            placeholder = query.message
            try:
                await query.edit_message_text(text=placeholder_text)
            except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
                logger.warning(f"[databases/kojo/tg_bot/bot_services/ai_communication_service.py] (RuntimeError, ConnectionError, TimeoutError, OSError): {e}")
        else:
            # Сценарий б: обычный ввод текста
            # [правило ios] 1. сначала шлем новое сообщение (плашку)
            placeholder = await context.bot.send_message(chat_id=chat_id, text=placeholder_text)
            # 2. фиксируем новый якорь только в сессии
            user_data['last_ai_msg_id'] = placeholder.message_id
            # 3. только теперь удаляем текст пользователя и старое меню
            if update.message:
                try:
                    await update.message.delete()
                except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
                    logger.warning(f"[databases/kojo/tg_bot/bot_services/ai_communication_service.py] (RuntimeError, ConnectionError, TimeoutError, OSError): {e}")
            await cleanup_previous_menu(context, user_id, exclude_id=placeholder.message_id)
            # 4. после зачистки обновляем якорь в бд на новое сообщение
            await user_service.save_registration_message_id(user_id, placeholder.message_id)
            logger.debug("AI Workflow: New placeholder %s sent. Old UI cleaned.", placeholder.message_id)

        if placeholder is None:
            return

        # Анимация и запрос к llm
        animator = ThinkingAnimator(context, chat_id, placeholder)  # type: ignore[arg-type]
        await animator.start()

        try:
            nickname = update.effective_user.username or update.effective_user.first_name
            result = await self.get_ai_answer(user_id, user_text, nickname)
            await animator.stop()
            full_answer = result.get("answer", "Не удалось получить ответ.")

            # [критично] финальное обновление:
            # Если это callback — редактируем существующее
            # Если это текст — отправляем новое сообщение, затем удаляем placeholder
            if query:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=placeholder.message_id,
                    text=prepare_html_for_telegram(full_answer),
                    reply_markup=get_ai_chat_keyboard(),
                    parse_mode='HTML'
                )
                logger.info(f"✅ AI Workflow: Successfully updated window {placeholder.message_id} with answer.")
            else:
                # [правило ios] сначала отправляем новое сообщение с ответом
                answer_msg = await context.bot.send_message(
                    chat_id=chat_id,
                    text=prepare_html_for_telegram(full_answer),
                    reply_markup=get_ai_chat_keyboard(),
                    parse_mode='HTML'
                )
                # Регистрируем новый якорь в сессии
                user_data['last_ai_msg_id'] = answer_msg.message_id
                # Только теперь удаляем placeholder
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=placeholder.message_id)
                except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
                    logger.debug(f"Could not delete placeholder {placeholder.message_id}: {e}")
                # Чистим старое меню (но не трогаем новый ответ!)
                await cleanup_previous_menu(context, user_id, exclude_id=answer_msg.message_id)
                # Обновляем якорь в бд после зачистки
                await user_service.save_registration_message_id(user_id, answer_msg.message_id)
                logger.info(f"✅ AI Workflow: Successfully sent new answer {answer_msg.message_id}, deleted placeholder {placeholder.message_id}.")

        except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
            await animator.stop()
            logger.error(f"❌ AI Workflow Error: {e}")
            try:
                if query:
                    await context.bot.edit_message_text(
                        chat_id=chat_id, message_id=placeholder.message_id,
                        text="🔌 <b>Ошибка связи.</b>\nНе удалось получить ответ. Повторите запрос позже.",
                        reply_markup=get_ai_chat_keyboard(),
                        parse_mode='HTML'
                    )
                else:
                    # Для текстового режима тоже отправляем новое сообщение об ошибке
                    error_msg = await context.bot.send_message(
                        chat_id=chat_id,
                        text="🔌 <b>Ошибка связи.</b>\nНе удалось получить ответ. Повторите запрос позже.",
                        reply_markup=get_ai_chat_keyboard(),
                        parse_mode='HTML'
                    )
                    # Удаляем placeholder
                    try:
                        await context.bot.delete_message(chat_id=chat_id, message_id=placeholder.message_id)
                    except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
                        logger.warning(f"[databases/kojo/tg_bot/bot_services/ai_communication_service.py] (RuntimeError, ConnectionError, TimeoutError, OSError): {e}")
                # Обновляем якорь
                    user_data['last_ai_msg_id'] = error_msg.message_id
                    await user_service.save_registration_message_id(user_id, error_msg.message_id)
            except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
                logger.warning(f"[databases/kojo/tg_bot/bot_services/ai_communication_service.py] (RuntimeError, ConnectionError, TimeoutError, OSError): {e}")


    async def get_chat_history_paged(self, user_id: int, nickname: str) -> dict[str, Any]:
        """Запрашивает историю, переключаясь между Локальным и Удаленным сервером, форматирует на клиенте."""
        # Параметры из окружения
        from tg_bot.infrastructure.secrets_loader import SecretsLoader
        local_url = SecretsLoader.get("QUART_SERVER_URL", "http://RAG_quart-server:5000/internal/ai/history")
        shared_secret = SecretsLoader.get_required("INTERNAL_SHARED_SECRET")

        payload = {
            "bot_id": self.bot_id,
            "user_id": str(user_id),
            "user_nickname": nickname
        }

        # Режим а: пробуем прямую локальную связь (самый быстрый путь)
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.post(local_url, json=payload, headers={"X-Internal-Token": shared_secret})
                if resp.status_code == 200:
                    logger.info("📡 [history] получено напрямую через local master")
                    data = resp.json()
                    raw_msgs = data.get("messages", [])
                    # Форматируем здесь
                    pages = self.format_history_to_pages(raw_msgs)
                    return {"status": "success", "pages": pages}
        except (RuntimeError, ConnectionError, TimeoutError, OSError, httpx.HTTPError):
            logger.info("🌐 [history] master недоступен напрямую, переключаюсь на gateway...")

        # Режим б: через gatewayclient с circuit breaker + hmac
        if self._gateway:
            try:
                response = await self._gateway._request("POST", "/api/ai/history", json=payload)
                if response.status_code == 200:
                    logger.info("☁️ [history] получено через remote gateway client")
                    data = response.json()
                    raw_msgs = data.get("messages", [])
                    pages = self.format_history_to_pages(raw_msgs)
                    return {"status": "success", "pages": pages}
            except CircuitOpenError:
                logger.warning("Circuit Open For History Gateway, Falling Back To Direct Httpx")
            except (httpx.HTTPError, ConnectionError, TimeoutError) as e:
                logger.error(f"Gateway history failed: {e}, falling back to direct httpx")

        # Ultimate Fallback: Legacy Httpx Remote Call
        remote_url = f"{self.quart_url}/api/ai/history"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(remote_url, json=payload)
                if resp.status_code == 200:
                    logger.info("☁️ [history] получено через remote gateway (legacy httpx)")
                    data = resp.json()
                    raw_msgs = data.get("messages", [])
                    pages = self.format_history_to_pages(raw_msgs)
                    return {"status": "success", "pages": pages}
        except (RuntimeError, ConnectionError, TimeoutError, OSError, httpx.HTTPError) as e:
            logger.error(f"❌ [History] Ошибка получения истории по всем путям: {e}")

        return {"status": "error", "pages": ["⚠️ Не удалось загрузить историю."]}


    def format_history_to_pages(self, raw_messages: list[Any], limit: int = 3800) -> list[Any]:
        """Превращает сырой JSON в отформатированные страницы для Telegram."""
        full_blocks = []

        for msg in raw_messages:
            role = msg.get('role', 'human')
            icon = "👤" if role == 'human' else "🤖"
            sender = "Вы" if role == 'human' else "Бариста"

            # Используем наш существующий _prepare_html, чтобы ссылки и жирность работали!
            content = prepare_html_for_telegram(msg.get('content', ''))

            time_str = ""
            if msg.get('created_at'):
                try:
                    dt = parse_date(msg['created_at'])
                    time_str = f" <i>({dt.strftime('%H:%M')})</i>"
                except (ValueError, TypeError, OverflowError):
                    logger.warning("[databases/kojo/tg_bot/bot_services/ai_communication_service.py] Date Parse Error")

            full_blocks.append(f"<b>{icon} {sender}</b>{time_str}:\n{content}\n\n")

        # Нарезка на страницы
        pages = []
        current_page = ""
        for block in full_blocks:
            if len(current_page) + len(block) > limit:
                pages.append(current_page.strip())
                current_page = block
            else:
                current_page += block

        if current_page:
            pages.append(current_page.strip())

        return pages if pages else ["История сообщений пока пуста."]


    async def get_brewing_guide(self, product_name: str, description: str, method: Optional[str] = None) -> str:
        """Главный оркестратор: определяет тип продукта и вызывает нужный генератор."""
        logger.info(f"👨‍🍳 [AI-Expert] Начало работы над лотом: {product_name}")

        is_tea = any(word in product_name.lower() or word in description.lower()
                     for word in ['чай', 'tea', 'улун', 'пуэр', 'габа', 'те гуань', 'да хун', 'матча'])

        if is_tea:
            prompt = self._build_tea_prompt(product_name, description, method)
        else:
            prompt = self._build_coffee_prompt(product_name, description, method)

        logger.debug("Prompt built for %s. Method: %s", "TEA" if is_tea else "COFFEE", method)
        return await self._execute_brewing_request(prompt, "tea" if is_tea else "coffee")


    async def _execute_brewing_request(self, prompt: str, log_label: str) -> str:
        """Выполняет запрос к Quart-серверу."""
        data = {
            "bot_id": self.bot_id,
            "user_id": f"system_expert_{log_label}",
            "topic": prompt,
            "is_direct": True
        }

        # Primary: Gatewayclient With Circuit Breaker + HMAC
        if self._gateway:
            try:
                response = await self._gateway._request("POST", "", json=data)
                if response.status_code == 200:
                    answer = cast(str, response.json().get("answer", "Ошибка получения данных."))
                    logger.info(f"✅ [AI-Expert] Рецепт ({log_label}) успешно сгенерирован.")
                    return answer
                return "⚠️ Мастер сейчас занят, попробуйте через минуту."
            except CircuitOpenError:
                logger.warning("Circuit Open For Brewing Request, Falling Back To Legacy Httpx")
            except (httpx.HTTPError, ConnectionError, TimeoutError) as e:
                logger.error(f"Gateway brewing request failed: {e}, falling back to legacy httpx")

        # Fallback: Legacy Httpx
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(self.quart_url, json=data)
                if resp.status_code == 200:
                    answer = cast(str, resp.json().get("answer", "Ошибка получения данных."))
                    logger.info(f"✅ [AI-Expert] Рецепт ({log_label}) успешно сгенерирован.")
                    return answer
                return "⚠️ Мастер сейчас занят, попробуйте через минуту."
        except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
            logger.error(f"❌ [AI-Expert] Error: {e}")
            return "🔌 Ошибка связи с мастерской вкуса."


    # Блок загрузки шаблонов
    def _read_config_file(self) -> str:
        """Безопасно читает файл ai_barista.txt."""
        path = os.path.join("config", "ai_barista.txt")
        if not os.path.exists(path):
            logger.error(f"❌ [AI-Config] Файл не найден: {path}")
            return ""
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
                return content
        except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
            logger.error(f"❌ [AI-Config] Ошибка чтения диска: {e}")
            return ""

    def _get_prompt_template(self, section_name: str) -> str:
        """Извлекает текст конкретной секции из общего конфига."""
        content = self._read_config_file()
        if not content:
            return ""

        start_tag = f"[{section_name}]"
        if start_tag not in content:
            logger.warning(f"⚠️ [AI-Config] Секция {section_name} отсутствует в ai_barista.txt")
            return ""

        # Парсинг блока до следующей открывающей скобки [
        start_idx = content.find(start_tag) + len(start_tag)
        end_idx = content.find("[", start_idx)

        template = content[start_idx:end_idx].strip() if end_idx != -1 else content[start_idx:].strip()
        logger.debug("AI Config: Template '%s' loaded, size=%d", section_name, len(template))
        return template

    # Блок сборки промптов
    def _build_tea_prompt(self, name: str, desc: str, method: Optional[str]) -> str:
        """Формирует промпт для чая через безопасную замену replace."""
        template = self._get_prompt_template("TEA_PROMPT")
        if not template:
            return f"Рецепт для чая {name}" # Fallback

        return template.replace("{name}", name).replace("{method}", method or "Классический").replace("{desc}", desc)

    def _build_coffee_prompt(self, name: str, desc: str, method: Optional[str]) -> str:
        """Формирует промпт для кофе через безопасную замену replace."""
        template = self._get_prompt_template("COFFEE_PROMPT")
        if not template:
            return f"Рецепт для кофе {name}" # Fallback

        return template.replace("{name}", name).replace("{method}", method or "V60").replace("{desc}", desc)


    async def get_ai_gift_greetings(self, prompt_data: str) -> list[str]:
        """
        Генерирует варианты поздравления, используя XML-теги для разделения.
        Гарантирует чистоту текста и наличие всех вариантов.
        """
        logger.info(f"✍️ [AI-Poet] Начало генерации (XML-mode) для: {prompt_data[:30]}...")

        template = self._get_prompt_template("GIFT_PROMPT")
        if not template:
            logger.error("❌ [ai-poet] шаблон gift_prompt не загружен!")
            return []

        # Безопасная вставка данных через replace
        prompt = template.replace("{prompt_data}", prompt_data)

        data = {
            "bot_id": self.bot_id,
            "user_id": "system_gift_writer",
            "topic": prompt,
            "is_direct": True
        }

        def _parse_gift_response(raw_text: str) -> list[str]:
            options = []
            for i in range(1, 4):
                tag = f"v{i}"
                pattern = f"<{tag}>(.*?)</{tag}>"
                match = re.search(pattern, raw_text, re.DOTALL | re.IGNORECASE)
                if match:
                    content = match.group(1).strip()
                    if content:
                        clean_content = prepare_html_for_telegram(content)
                        options.append(clean_content)
                        logger.debug("Parsed variation %d, size=%d", i, len(clean_content))
            if not options:
                logger.warning("⚠️ xml-теги не найдены. используем аварийный сплит по абзацам.")
                options = [opt.strip() for opt in raw_text.split("\n\n") if len(opt) > 30]
            return options[:3]

        # Primary: Gatewayclient With Circuit Breaker + HMAC
        if self._gateway:
            try:
                response = await self._gateway._request("POST", "", json=data)
                if response.status_code == 200:
                    raw_text = response.json().get("answer", "")
                    logger.debug("AI Poet Raw Response length: %d", len(raw_text))
                    return _parse_gift_response(raw_text)
                logger.error(f"❌ [AI-Poet] Gateway returned {response.status_code}")
                return []
            except CircuitOpenError:
                logger.warning("Circuit Open For Gift Greetings, Falling Back To Legacy")
            except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
                logger.error(f"Gateway gift greetings failed: {e}, falling back to legacy")

        # Fallback: Legacy Httpx
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(self.quart_url, json=data)
                if response.status_code == 200:
                    raw_text = response.json().get("answer", "")
                    logger.debug("AI Poet Raw Response length: %d", len(raw_text))
                    return _parse_gift_response(raw_text)
                logger.error(f"❌ [AI-Poet] Server returned {response.status_code}")
                return []
        except (RuntimeError, ConnectionError, TimeoutError, OSError) as e:
            logger.error(f"❌ [AI-Poet] Critical Error: {e}", exc_info=True)
            return []
