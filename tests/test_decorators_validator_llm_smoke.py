"""Smoke tests for decorators, validator, llm client."""



class TestDecoratorsImports:
    def test_auth_guard_import(self) -> None:
        from tg_bot.decorators import auth_guard
        assert callable(auth_guard)

    def test_auth_guard_returns_callable(self) -> None:
        from tg_bot.decorators import auth_guard
        decorator = auth_guard()
        assert callable(decorator)

    def test_auth_guard_staff_only(self) -> None:
        from tg_bot.decorators import auth_guard
        decorator = auth_guard(staff_only=True)
        assert callable(decorator)


class TestCallbackValidatorImports:
    def test_validate_callback_data_import(self) -> None:
        from tg_bot.callback_validator import validate_callback_data
        assert callable(validate_callback_data)

    def test_validate_callback_decorator_import(self) -> None:
        from tg_bot.callback_validator import validate_callback
        assert callable(validate_callback)

    def test_validate_callback_data_valid(self) -> None:
        from tg_bot.callback_validator import validate_callback_data
        result = validate_callback_data("test_data_123")
        assert result == "test_data_123"

    def test_validate_callback_data_empty(self) -> None:
        from tg_bot.callback_validator import validate_callback_data
        assert validate_callback_data(None) == ""
        assert validate_callback_data("") == ""


class TestLLMClientImports:
    def test_llm_client_import(self) -> None:
        from tg_bot.llm_client import LLMResponse, LLMStructuredClient
        assert LLMStructuredClient is not None
        assert LLMResponse is not None

    def test_llm_dataclasses_import(self) -> None:
        from tg_bot.llm_client import LLMMessage, LLMRequest, ResponseFormat
        assert LLMRequest is not None
        assert LLMMessage is not None
        assert ResponseFormat is not None

    def test_prompt_template_import(self) -> None:
        from tg_bot.llm_client import PromptTemplate
        template = PromptTemplate.coffee_shop_assistant()
        assert isinstance(template, str)

    def test_factory_import(self) -> None:
        from tg_bot.llm_client import create_llm_client
        assert callable(create_llm_client)
