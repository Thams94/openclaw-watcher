"""通知后端工厂。

新增后端（例如卡通形象小人提醒）时：
1. 新建 notifier/mascot.py，实现 base.Notifier 接口；
2. 在下方 _BACKENDS 注册名字；
3. config.json 里把 "notifier" 改成对应名字即可。
"""

from .base import Notifier
from .console import ConsoleNotifier
from .popup import PopupNotifier

_BACKENDS = {
    "popup": lambda cfg: PopupNotifier(
        timeout_seconds=cfg.get("popup_timeout_seconds", 25),
        sound=cfg.get("sound", True),
    ),
    "console": lambda cfg: ConsoleNotifier(),
}


def create_notifier(cfg):
    name = cfg.get("notifier", "popup")
    factory = _BACKENDS.get(name)
    if factory is None:
        raise ValueError(f"未知通知后端：{name}，可选：{sorted(_BACKENDS)}")
    return factory(cfg)


__all__ = ["Notifier", "create_notifier"]
