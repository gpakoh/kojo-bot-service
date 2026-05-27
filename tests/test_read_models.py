# Tests/test_read_models.py
from typing import Any

import pytest

from tg_bot.read_models.admin import (
    CourierMenuView,
    LogoSettingsView,
    PickupPointView,
    ProxySettingsView,
    UserDetailsView,
    UserListView,
    UsersMenuView,
    build_user_list_view,
)
from tg_bot.read_models.keyboards import (
    build_courier_menu,
    build_logo_mgmt,
    build_proxy_mgmt,
    build_user_details_keyboard,
    build_user_list_keyboard,
    build_users_menu,
)


class TestReadModels:
    def test_user_list_view_immutable(self) -> Any:
        v = UserListView(user_id=123, db_id=1, fio="Иванов", status="approved", role="user", registered_at="01.01.2025")
        with pytest.raises(Exception):
            v.fio = "Петров"

    def test_users_menu_view_creation(self) -> Any:
        v = UsersMenuView(
            pending_count=5, approved_count=10, blocked_count=2,
            user_count=8, manager_count=1, admin_count=1
        )
        assert v.pending_count == 5

    def test_logo_settings_view(self) -> Any:
        v = LogoSettingsView(has_logo=True, logo_type="photo", logo_id="abc123")
        assert v.has_logo is True
        assert v.logo_type == "photo"

    def test_proxy_settings_view_defaults(self) -> Any:
        v = ProxySettingsView(has_proxy_url=False)
        assert v.is_enabled is True
        assert v.proxy_url is None

    def test_courier_menu_view(self) -> Any:
        v = CourierMenuView(is_enabled=True, cities=[{"name": "Москва", "cost": 300.0, "days": "1-2"}])
        assert len(v.cities) == 1
        assert v.cities[0]["name"] == "Москва"

    def test_pickup_point_view(self) -> Any:
        v = PickupPointView(
            idx=0, name="Точка 1", address="ул. Пушкина", schedule="9-21",
            is_active=True, editable_fields=["address"]
        )
        assert v.is_active is True

    def test_build_user_list_view(self) -> Any:
        class MockUser:
            telegram_id = 123
            id = 1
            fio = "Иванов И.И."
            status = type('obj', (object,), {'value': 'approved'})()
            role = type('obj', (object,), {'value': 'user'})()
            created_at = type('obj', (object,), {'strftime': lambda s, f: '01.01.2025'})()
        v = build_user_list_view(MockUser())
        assert v.user_id == 123
        assert v.db_id == 1
        assert v.fio == "Иванов И.И."


class TestKeyboardBuilders:
    def test_build_users_menu(self) -> Any:
        v = UsersMenuView(
            pending_count=3, approved_count=10, blocked_count=1,
            user_count=8, manager_count=2, admin_count=1
        )
        kb = build_users_menu(v)
        assert kb is not None
        assert len(kb.inline_keyboard) == 7

    def test_build_user_list_keyboard(self) -> Any:
        items = [
            UserListView(
                user_id=1, db_id=10, fio="Иванов",
                status="approved", role="user", registered_at="01.01.2025"
            ),
            UserListView(
                user_id=2, db_id=20, fio="Петров",
                status="pending", role="manager", registered_at="02.02.2025"
            ),
        ]
        kb = build_user_list_keyboard(items, "approved")
        assert len(kb.inline_keyboard) == 3  # 2 users + back button

    def test_build_user_details_keyboard_admin(self) -> Any:
        v = UserDetailsView(db_id=1, telegram_id=123, fio="Админ", phone="+7", email="a@b.com",
                             status_label="✅", role_label="👑", is_blocked=False, is_manager=False, is_admin=True)
        kb = build_user_details_keyboard(v, "approved")
        assert len(kb.inline_keyboard) == 6  # approve + demote + reset + back + close

    def test_build_user_details_keyboard_user(self) -> Any:
        v = UserDetailsView(db_id=1, telegram_id=123, fio="Пользователь", phone="+7", email="a@b.com",
                             status_label="✅", role_label="👤", is_blocked=False, is_manager=False, is_admin=False)
        kb = build_user_details_keyboard(v, "approved")
        btn_texts = [row[0].text for row in kb.inline_keyboard]
        assert "⬆️ Повысить до менеджера" in btn_texts

    def test_build_logo_mgmt_with_logo(self) -> Any:
        v = LogoSettingsView(has_logo=True, logo_type="photo", logo_id="abc")
        kb = build_logo_mgmt(v)
        texts = [btn for row in kb.inline_keyboard for btn in row]
        assert any("Заменить" in b.text for b in texts)
        assert any("Удалить" in b.text for b in texts)

    def test_build_logo_mgmt_no_logo(self) -> Any:
        v = LogoSettingsView(has_logo=False, logo_type="photo")
        kb = build_logo_mgmt(v)
        texts = [btn for row in kb.inline_keyboard for btn in row]
        assert any("Загрузить" in b.text for b in texts)

    def test_build_proxy_mgmt_disabled(self) -> Any:
        v = ProxySettingsView(has_proxy_url=True, proxy_url="socks5://x", is_enabled=False)
        kb = build_proxy_mgmt(v)
        texts = [btn for row in kb.inline_keyboard for btn in row]
        assert any("🟢 Включить" in b.text for b in texts)

    def test_build_courier_menu(self) -> Any:
        v = CourierMenuView(is_enabled=True, cities=[{"name": "СПб", "cost": 250.0, "days": "2-3"}])
        kb = build_courier_menu(v)
        assert len(kb.inline_keyboard) >= 3
