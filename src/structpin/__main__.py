"""اجرای برنامه با دستور: python -m structpin

import این ماژول هیچ پنجره‌ای نمی‌سازد؛ فقط زمانی که به‌صورت برنامه اجرا شود
تابع main از app فراخوانی می‌شود.
"""

from __future__ import annotations

from structpin.app import main

if __name__ == "__main__":
    main()
