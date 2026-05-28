"""Unit tests for tg_bot/handlers/info.py."""
from telegram.ext import ConversationHandler


class TestInfoConversation:
    def test_is_conversation_handler(self):
        from tg_bot.handlers.info import info_conversation

        assert isinstance(info_conversation, ConversationHandler)

    def test_has_entry_points(self):
        from tg_bot.handlers.info import info_conversation

        assert hasattr(info_conversation, "entry_points")

    def test_has_states_and_fallbacks(self):
        from tg_bot.handlers.info import info_conversation

        assert info_conversation.entry_points == []
        assert info_conversation.states == {}
        assert info_conversation.fallbacks == []

    def test_import_does_not_raise(self):
        from tg_bot.handlers.info import info_conversation  # noqa: F811

        assert info_conversation is not None
