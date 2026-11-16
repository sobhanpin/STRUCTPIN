"""نقطهٔ ورود رسمی برنامهٔ دسکتاپ STRUCTPIN.

این ماژول هنگام import هیچ پنجره‌ای نمی‌سازد و هیچ حلقهٔ رویدادی را اجرا نمی‌کند.
اجرای واقعی تنها از طریق تابع main() انجام می‌شود.
"""

from __future__ import annotations

from structpin.ui.main_window import main as _run_main_window

__all__ = ["main"]


def main() -> None:
    """ساخت پنجرهٔ اصلی STRUCTPIN و اجرای حلقهٔ رویدادهای Tkinter.

    خطاهای Tkinter (مثلاً نبود نمایشگر) پنهان نمی‌شوند و به فراخواننده منتقل می‌شوند.
    """
    _run_main_window()


if __name__ == "__main__":
    main()
