# -*- coding: utf-8 -*-
"""
本地覆盖配置示例。复制为本 config/local_settings.py 后填入真实凭据。
local_settings.py 已在 .gitignore 中，不会被版本控制。
"""

# 方式 A：用环境变量（推荐）
# export MYSQL_PASSWORD=your_real_password
# export MYSQL_USER=root

# 方式 B：直接在此覆盖
DATABASE_CONFIG = {
    'mysql': {
        'host': 'localhost',
        'port': 3306,
        'user': 'root',
        'password': 'your_real_password_here',  # ← 填入真实密码
        'database': 'news_hotspot',
        'charset': 'utf8mb4'
    }
}
