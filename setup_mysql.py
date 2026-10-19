#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MySQL数据库设置脚本
用于创建数据库、表和测试连接
"""

import mysql.connector
import getpass
import sys
from config.settings import DATABASE_CONFIG

def test_connection(host, port, user, password):
    """测试MySQL连接"""
    try:
        conn = mysql.connector.connect(
            host=host,
            port=port,
            user=user,
            password=password
        )
        print(f"✅ MySQL连接成功！")
        print(f"   服务器版本: {conn.get_server_info()}")
        conn.close()
        return True
    except mysql.connector.Error as e:
        print(f"❌ MySQL连接失败: {e}")
        return False

def create_database(host, port, user, password, database_name):
    """创建数据库"""
    try:
        # 连接MySQL服务器
        conn = mysql.connector.connect(
            host=host,
            port=port,
            user=user,
            password=password
        )
        cursor = conn.cursor()
        
        # 创建数据库
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {database_name} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        print(f"✅ 数据库 '{database_name}' 创建成功！")
        
        # 使用数据库
        cursor.execute(f"USE {database_name}")
        
        # 创建新闻文章表
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS news_articles (
            id INT AUTO_INCREMENT PRIMARY KEY,
            news_id VARCHAR(100) UNIQUE NOT NULL,
            title VARCHAR(500) NOT NULL,
            content TEXT NOT NULL,
            source VARCHAR(100) NOT NULL,
            author VARCHAR(100),
            publish_time DATETIME,
            url VARCHAR(500),
            comments_count INT DEFAULT 0,
            likes_count INT DEFAULT 0,
            shares_count INT DEFAULT 0,
            crawl_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            category VARCHAR(100),
            tags VARCHAR(500),
            INDEX idx_source (source),
            INDEX idx_publish_time (publish_time),
            INDEX idx_category (category)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
        
        cursor.execute(create_table_sql)
        print("✅ 新闻文章表创建成功！")
        
        # 显示表结构
        cursor.execute("DESCRIBE news_articles")
        columns = cursor.fetchall()
        print("\n📋 表结构:")
        for column in columns:
            print(f"   {column[0]} - {column[1]}")
        
        cursor.close()
        conn.close()
        return True
        
    except mysql.connector.Error as e:
        print(f"❌ 创建数据库失败: {e}")
        return False

def update_config_password(new_password):
    """更新配置文件中的密码"""
    config_file = "config/settings.py"
    
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 替换密码
        old_password = DATABASE_CONFIG['mysql']['password']
        content = content.replace(f"'password': '{old_password}'", f"'password': '{new_password}'")
        
        with open(config_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✅ 配置文件密码已更新")
        return True
        
    except Exception as e:
        print(f"❌ 更新配置文件失败: {e}")
        return False

def main():
    """主函数"""
    print("🔧 MySQL数据库设置向导")
    print("=" * 50)
    
    # 从配置文件读取默认值
    config = DATABASE_CONFIG['mysql']
    host = config['host']
    port = config['port']
    user = config['user']
    database_name = config['database']
    
    print(f"数据库主机: {host}")
    print(f"端口: {port}")
    print(f"用户名: {user}")
    print(f"数据库名: {database_name}")
    print()
    
    # 测试当前配置的密码
    current_password = config['password']
    print("🔍 测试当前配置的密码...")
    
    if test_connection(host, port, user, current_password):
        print("当前配置的密码可用，继续创建数据库...")
        password = current_password
    else:
        print("当前配置的密码不正确，请输入正确的MySQL root密码:")
        password = getpass.getpass("MySQL root密码: ")
        
        if test_connection(host, port, user, password):
            print("密码验证成功！")
            # 询问是否更新配置文件
            update_choice = input("是否要更新配置文件中的密码? (y/n): ").lower()
            if update_choice == 'y':
                update_config_password(password)
        else:
            print("密码验证失败，请检查MySQL安装和密码设置。")
            return False
    
    # 创建数据库和表
    print("\n🏗️ 创建数据库和表...")
    if create_database(host, port, user, password, database_name):
        print("\n✅ 数据库设置完成！")
        print("\n📝 接下来您可以:")
        print("   1. 运行 python run.py 启动项目")
        print("   2. 测试数据库连接: python -c \"from database.db_manager import MySQLManager; MySQLManager()\"")
        return True
    else:
        print("\n❌ 数据库设置失败！")
        return False

if __name__ == "__main__":
    main() 