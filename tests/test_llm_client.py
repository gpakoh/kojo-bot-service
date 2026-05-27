# Tests For LLM Structured Client
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from tg_bot.llm_client import (
    LLMMessage,
    LLMRequest,
    LLMStructuredClient,
    PromptTemplate,
    ResponseFormat,
    create_llm_client,
)


class _AsyncCtxManager:
    """Helper to make a value work as async context manager."""
    def __init__(self, value) -> None:
        self.value = value
    async def __aenter__(self) -> Any:
        return self.value
    async def __aexit__(self, *args) -> Any:
        pass


class TestLLMMessage:
    """Tests for LLMMessage."""

    def test_message_creation(self) -> Any:
        msg = LLMMessage(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"

    def test_message_to_dict(self) -> Any:
        msg = LLMMessage(role="system", content="You are helpful")
        d = {"role": msg.role, "content": msg.content}
        assert d == {"role": "system", "content": "You are helpful"}

    def test_message_list_to_dict(self) -> Any:
        messages = [
            LLMMessage(role="system", content="System prompt"),
            LLMMessage(role="user", content="User question"),
        ]
        d = [{"role": m.role, "content": m.content} for m in messages]
        assert len(d) == 2
        assert d[0]["role"] == "system"


class TestLLMRequest:
    """Tests for LLMRequest."""

    def test_request_creation(self) -> Any:
        messages = [LLMMessage(role="user", content="Hi")]
        request = LLMRequest(model="gpt-4", messages=messages)

        assert request.model == "gpt-4"
        assert len(request.messages) == 1

    def test_request_to_dict(self) -> Any:
        messages = [LLMMessage(role="user", content="Hi")]
        request = LLMRequest(
            model="gpt-4",
            messages=messages,
            temperature=0.5,
            response_format=ResponseFormat.JSON,
        )

        d = request.to_dict()

        assert d["model"] == "gpt-4"
        assert d["temperature"] == 0.5
        assert d["response_format"]["type"] == "json_object"
        assert len(d["messages"]) == 1

    def test_request_without_json_mode(self) -> Any:
        messages = [LLMMessage(role="user", content="Hi")]
        request = LLMRequest(model="gpt-4", messages=messages)

        d = request.to_dict()

        assert "response_format" not in d


class TestLLMStructuredClient:
    """Tests for LLMStructuredClient."""

    @pytest.fixture
    def client(self) -> Any:
        mock_middleware = MagicMock()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=MagicMock(
            status_code=200,
            json=lambda: {
                "choices": [{
                    "message": {"content": "default"},
                    "finish_reason": "stop",
                }]
            }
        ))
        mock_middleware.client = MagicMock(return_value=_AsyncCtxManager(mock_client))
        return LLMStructuredClient(
            base_url="http://localhost:5000",
            api_key="test-key",
            model="gpt-4",
            http_middleware=mock_middleware,
        )

    def test_client_initialization(self, client) -> Any:
        assert client.base_url == "http://localhost:5000"
        assert client.api_key == "test-key"
        assert client.model == "gpt-4"

    def test_build_request_separates_system_and_user(self, client) -> Any:
        request = client.build_request(
            system_prompt="You are a helpful assistant.",
            user_input="What is coffee?",
        )

        assert len(request.messages) == 2
        assert request.messages[0].role == "system"
        assert request.messages[0].content == "You are a helpful assistant."
        assert request.messages[1].role == "user"
        assert request.messages[1].content == "What is coffee?"

    def test_build_request_with_history(self, client) -> Any:
        history = [
            LLMMessage(role="user", content="I like dark roast"),
            LLMMessage(role="assistant", content="Great! Dark roast is bold and rich."),
        ]

        request = client.build_request(
            system_prompt="You are a coffee expert.",
            user_input="What do you recommend?",
            conversation_history=history,
        )

        assert len(request.messages) == 4
        assert request.messages[0].role == "system"
        assert request.messages[1].role == "user"
        assert request.messages[1].content == "I like dark roast"
        assert request.messages[2].role == "assistant"
        assert request.messages[3].role == "user"

    def test_build_request_json_mode(self, client) -> Any:
        request = client.build_request(
            system_prompt="Return JSON.",
            user_input="Get info",
            use_json_mode=True,
        )

        assert request.response_format == ResponseFormat.JSON

    @pytest.mark.asyncio
    async def test_chat_success(self, client) -> Any:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = lambda: {
            "choices": [{
                "message": {"content": "Coffee is great!"},
                "finish_reason": "stop",
            }]
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        client._http_middleware.client = MagicMock(return_value=_AsyncCtxManager(mock_client))

        response = await client.chat(
            system_prompt="You are a coffee expert.",
            user_input="What is coffee?",
        )

        assert response.content == "Coffee is great!"
        assert response.finish_reason == "stop"

    @pytest.mark.asyncio
    async def test_chat_json_mode(self, client) -> Any:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = lambda: {
            "choices": [{
                "message": {"content": '{"product_name": "Ethiopia", "price": 500}'},
                "finish_reason": "stop",
            }]
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        client._http_middleware.client = MagicMock(return_value=_AsyncCtxManager(mock_client))

        json_data = await client.chat_json(
            system_prompt="Recommend coffee.",
            user_input="I want something fruity",
            expected_fields=["product_name", "price"],
        )

        assert json_data["product_name"] == "Ethiopia"
        assert json_data["price"] == 500

    @pytest.mark.asyncio
    async def test_chat_json_invalid_response(self, client) -> Any:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = lambda: {
            "choices": [{
                "message": {"content": "Not valid JSON"},
                "finish_reason": "stop",
            }]
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        client._http_middleware.client = MagicMock(return_value=_AsyncCtxManager(mock_client))

        json_data = await client.chat_json(
            system_prompt="Return JSON.",
            user_input="test",
            expected_fields=["name"],
        )

        assert json_data is None


class TestPromptTemplate:
    """Tests for prompt templates."""

    def test_coffee_shop_assistant(self) -> Any:
        template = PromptTemplate.coffee_shop_assistant()

        assert "coffee shop assistant" in template.lower()
        assert "Russian" in template

    def test_order_assistance(self) -> Any:
        template = PromptTemplate.order_assistance()

        assert "order" in template.lower()
        assert "cart" in template.lower()

    def test_product_recommendation(self) -> Any:
        template = PromptTemplate.product_recommendation()

        assert "JSON" in template
        assert "product_name" in template
        assert "price" in template


class TestCreateLLMClient:
    """Tests for factory function."""

    def test_create_client_with_config(self) -> Any:
        mock_config = MagicMock()
        mock_config.get = MagicMock(side_effect=lambda k, d="": {
            "QUART_SERVER_URL": "http://custom:8000",
            "OPENAI_API_KEY": "key-123",
            "LLM_MODEL": "gpt-3.5",
        }.get(k, d))

        mock_middleware = AsyncMock()
        client = create_llm_client(http_middleware=mock_middleware, app_config=mock_config)

        assert client.base_url == "http://custom:8000"
        assert client.api_key == "key-123"
        assert client.model == "gpt-3.5"

    def test_create_client_defaults(self) -> Any:
        mock_config = MagicMock()
        mock_config.get = MagicMock(side_effect=lambda k, d="": {
            "QUART_SERVER_URL": "http://localhost:5000",
            "OPENAI_API_KEY": "",
            "LLM_MODEL": "gpt-4",
        }.get(k, d))

        mock_middleware = AsyncMock()
        client = create_llm_client(http_middleware=mock_middleware, app_config=mock_config)

        assert client.base_url == "http://localhost:5000"
        assert client.model == "gpt-4"
