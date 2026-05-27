from typing import Any

# Tests/test_admin_package.py


class TestAdminPackage:
    def test_users_module_imports(self) -> Any:
        from tg_bot.handlers.admin_panel import (
            handle_user_action,
            show_user_details,
            show_user_list_by_role,
            show_user_list_by_status,
            show_users_menu,
        )
        assert callable(show_users_menu)
        assert callable(show_user_list_by_role)
        assert callable(show_user_list_by_status)
        assert callable(show_user_details)
        assert callable(handle_user_action)

    def test_callbacks_protocol_imports(self) -> Any:
        from tg_bot.callbacks import (
            admin_dispatch,
        )
        assert hasattr(admin_dispatch, 'orders')
        assert hasattr(admin_dispatch, 'communication')
        assert hasattr(admin_dispatch, 'pickup')
        assert hasattr(admin_dispatch, 'logo')
        assert hasattr(admin_dispatch, 'proxy')
        assert hasattr(admin_dispatch, 'courier')
