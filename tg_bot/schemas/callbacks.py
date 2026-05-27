# Tg_bot/schemas/callbacks.py
# Pydantic Models For Callback Data Validation
# Provides Strict Type Validation For Incoming Telegram Callbacks

from typing import Literal, Optional

from pydantic import BaseModel, Field, ValidationError


class ProductCallback(BaseModel):
    """Product-related callbacks: prod_sel_123, add_to_cart_123"""
    product_id: int = Field(gt=0, description="Product ID must be positive")
    action: Optional[str] = None


class CategoryCallback(BaseModel):
    """Category selection: cat_sel_123"""
    category_id: int = Field(gt=0)
    action: Optional[Literal["list", "all"]] = None


class CartCallback(BaseModel):
    """Cart operations: c_inc_123, c_dec_123, c_del_123"""
    action: Literal["inc", "dec", "del", "undo", "qty_grid"]
    product_id: int = Field(gt=0)


class FavoriteCallback(BaseModel):
    """Favorite operations: fav_to_cart_123, f_inc_123"""
    action: Literal["add", "remove", "toggle", "to_cart", "inc", "dec", "remove", "notify", "qty_grid"]
    product_id: int = Field(gt=0)


class OrderCallback(BaseModel):
    """Order-related callbacks: user_order_details_123"""
    order_id: int = Field(gt=0)


class OrderActionCallback(BaseModel):
    """Order actions: order_action_123"""
    action: str
    order_id: int = Field(gt=0)


class UserActionCallback(BaseModel):
    """User management: approve_123, decline_123"""
    action: Literal["approve", "decline", "view", "ban", "unban"]
    user_id: int = Field(gt=0)


class AddressCallback(BaseModel):
    """Address management: addr_del_123, addr_def_123"""
    action: Literal["del", "def", "view", "edit"]
    address_id: int = Field(gt=0)


class DeliveryCallback(BaseModel):
    """Delivery selection: delivery_yandex, delivery_pickup"""
    delivery_type: Literal["yandex", "pickup", "courier", "self"]


class CheckoutCallback(BaseModel):
    """Checkout flow"""
    step: Optional[Literal["address", "payment", "confirm", "back"]] = None


class NavigationCallback(BaseModel):
    """Navigation: back_to_cat, back_to_prod_list"""
    screen: Literal["categories", "products", "cart", "menu", "main"]
    category_id: Optional[int] = Field(default=None, gt=0)


class InfoCallback(BaseModel):
    """Info/CMS pages: info_go_123"""
    page_id: Optional[int] = Field(default=None, gt=0)
    action: Optional[Literal["add", "edit", "del", "move_up", "move_down"]] = None


class SettingsCallback(BaseModel):
    """User settings"""
    setting: Optional[Literal["notifications", "language", "theme"]] = None
    value: Optional[str] = None


class AIChatCallback(BaseModel):
    """AI chat: ai_chat_history, ai_chat_start"""
    action: Optional[Literal["history", "start", "back"]] = None
    page: Optional[int] = Field(default=0, ge=0)


# Registry For Parsing Callbacks
CALLBACK_PARSERS = {
    "prod_sel_": ProductCallback,
    "add_to_cart_": ProductCallback,
    "cat_sel_": CategoryCallback,
    "c_inc_": CartCallback,
    "c_dec_": CartCallback,
    "c_del_": CartCallback,
    "c_undo_": CartCallback,
    "c_q_grid_": CartCallback,
    "fav_to_cart_": FavoriteCallback,
    "f_inc_": FavoriteCallback,
    "f_dec_": FavoriteCallback,
    "fav_remove_": FavoriteCallback,
    "f_q_grid_": FavoriteCallback,
    "user_order_details_": OrderCallback,
    "order_action_": OrderActionCallback,
    "approve_": UserActionCallback,
    "decline_": UserActionCallback,
    "addr_del_": AddressCallback,
    "addr_def_": AddressCallback,
    "addr_view_": AddressCallback,
    "delivery_yandex": DeliveryCallback,
    "delivery_pickup": DeliveryCallback,
    "delivery_courier": DeliveryCallback,
    "back_to_cat": NavigationCallback,
    "back_to_prod_list": NavigationCallback,
    "info_go_": InfoCallback,
    "ai_chat_history": AIChatCallback,
    "ai_chat_start": AIChatCallback,
}

# Maps Prefixes With Data Encoded In The Prefix Itself (no numeric suffix)
PREFIX_DATA = {
    "delivery_yandex": {"delivery_type": "yandex"},
    "delivery_pickup": {"delivery_type": "pickup"},
    "delivery_courier": {"delivery_type": "courier"},
    "back_to_cat": {"screen": "categories"},
    "back_to_prod_list": {"screen": "products"},
    "ai_chat_history": {"action": "history"},
    "ai_chat_start": {"action": "start"},
}

# Maps Prefixes To Their Embedded Action Values For Models With Action Fields
PREFIX_ACTIONS = {
    "c_inc_": "inc",
    "c_dec_": "dec",
    "c_del_": "del",
    "c_undo_": "undo",
    "c_q_grid_": "qty_grid",
    "fav_to_cart_": "to_cart",
    "f_inc_": "inc",
    "f_dec_": "dec",
    "fav_remove_": "remove",
    "f_q_grid_": "qty_grid",
    "approve_": "approve",
    "decline_": "decline",
    "addr_del_": "del",
    "addr_def_": "def",
    "addr_view_": "view",
}


def parse_callback_data(data: Optional[str]) -> Optional[BaseModel]:
    if not data:
        return None

    for prefix, model_class in CALLBACK_PARSERS.items():
        if data.startswith(prefix):
            suffix = data[len(prefix):]

            if not suffix:
                kw = PREFIX_DATA.get(prefix, {})
                try:
                    return model_class(**kw)  # type: ignore[no-any-return]
                except (ValidationError, ValueError):
                    return None

            if suffix.isdigit():
                numeric_id = int(suffix)
                fields = list(model_class.model_fields.keys())  # type: ignore[attr-defined]

                action = PREFIX_ACTIONS.get(prefix)
                try:
                    if action and 'action' in fields:
                        id_field = next(f for f in fields if f != 'action')
                        return model_class(action=action, **{id_field: numeric_id})  # type: ignore[no-any-return]
                    id_field = fields[0]
                    return model_class(**{id_field: numeric_id})  # type: ignore[no-any-return]
                except (ValidationError, ValueError):
                    return None

    return None


__all__ = [
    'ProductCallback',
    'CategoryCallback',
    'CartCallback',
    'FavoriteCallback',
    'OrderCallback',
    'OrderActionCallback',
    'UserActionCallback',
    'AddressCallback',
    'DeliveryCallback',
    'CheckoutCallback',
    'NavigationCallback',
    'InfoCallback',
    'SettingsCallback',
    'AIChatCallback',
    'parse_callback_data',
    'CALLBACK_PARSERS',
]
