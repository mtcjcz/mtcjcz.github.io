"""
数据库初始化脚本 - 修复答案格式
"""

import pymysql
import json

# 数据库配置
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',  # 修改为您的MySQL用户名
    'password': '19848377',  # 修改为您的MySQL密码
    'charset': 'utf8'
}

DATABASE_NAME = 'test3'

def create_database_and_tables():
    """创建数据库和所有表"""

    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()

    try:
        # 创建数据库
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DATABASE_NAME} CHARACTER SET utf8 COLLATE utf8_general_ci")
        print(f"✓ 数据库 '{DATABASE_NAME}' 创建成功")

        cursor.execute(f"USE {DATABASE_NAME}")
        cursor.execute("SET NAMES utf8")

        # 删除旧表（重新创建）
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
        tables = ['practice_records', 'exam_records', 'exam_questions', 'exams', 'questions', 'users']
        for table in tables:
            cursor.execute(f"DROP TABLE IF EXISTS {table}")
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")

        # 创建用户表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INT PRIMARY KEY AUTO_INCREMENT,
                username VARCHAR(50) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL,
                role ENUM('student', 'teacher', 'admin') NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8
        """)
        print("✓ 表 'users' 创建成功")

        # 创建题目表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS questions (
                id INT PRIMARY KEY AUTO_INCREMENT,
                type ENUM('single', 'multiple', 'judge', 'essay') NOT NULL,
                content TEXT NOT NULL,
                options TEXT,
                answer TEXT NOT NULL,
                score INT DEFAULT 0,
                created_by INT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8
        """)
        print("✓ 表 'questions' 创建成功")

        # 创建考试表（添加时间字段）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS exams (
                id INT PRIMARY KEY AUTO_INCREMENT,
                title VARCHAR(100) NOT NULL,
                description TEXT,
                single_count INT DEFAULT 0,
                multiple_count INT DEFAULT 0,
                judge_count INT DEFAULT 0,
                essay_count INT DEFAULT 0,
                single_score INT DEFAULT 2,
                multiple_score INT DEFAULT 3,
                judge_score INT DEFAULT 2,
                essay_score INT DEFAULT 5,
                created_by INT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                valid_from DATETIME NOT NULL,
                valid_to DATETIME NOT NULL,
                duration_minutes INT DEFAULT 60,
                FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8
        """)
        print("✓ 表 'exams' 创建成功")

        # 创建考试题目关联表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS exam_questions (
                id INT PRIMARY KEY AUTO_INCREMENT,
                exam_id INT,
                question_id INT,
                FOREIGN KEY (exam_id) REFERENCES exams(id) ON DELETE CASCADE,
                FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8
        """)
        print("✓ 表 'exam_questions' 创建成功")

        # 创建考试记录表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS exam_records (
                id INT PRIMARY KEY AUTO_INCREMENT,
                student_id INT,
                exam_id INT,
                attempt_number INT DEFAULT 1,
                answers TEXT,
                total_score INT,
                start_time TIMESTAMP,
                submit_time TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (exam_id) REFERENCES exams(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8
        """)
        print("✓ 表 'exam_records' 创建成功")

        # 创建练习题记录表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS practice_records (
                id INT PRIMARY KEY AUTO_INCREMENT,
                student_id INT,
                question_id INT,
                answer TEXT,
                is_correct BOOLEAN,
                practice_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8
        """)
        print("✓ 表 'practice_records' 创建成功")

        conn.commit()
        print("\n✅ 所有表创建成功！")

    except Exception as e:
        print(f"❌ 创建表时出错: {e}")
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

def insert_initial_data():
    """插入初始数据 - 答案使用字母标识"""

    conn = pymysql.connect(**DB_CONFIG, database=DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("SET NAMES utf8")

    try:
        # 插入管理员
        cursor.execute("SELECT COUNT(*) FROM users WHERE role='admin'")
        if cursor.fetchone()[0] == 0:
            cursor.execute("""
                INSERT INTO users (username, password, role) VALUES 
                ('admin', 'admin123', 'admin')
            """)
            print("✓ 管理员账户创建成功")
            admin_id = cursor.lastrowid
        else:
            cursor.execute("SELECT id FROM users WHERE role='admin' LIMIT 1")
            admin_id = cursor.fetchone()[0]

        # 插入示例题目 - 答案使用字母
        sample_questions = [
            # 单选题
            ('single', 'Python中哪个关键字用于定义函数？',
             json.dumps(['def', 'function', 'define', 'func'], ensure_ascii=False),
             'A', 2, admin_id),

            ('single', '以下哪个不是Python的容器类型？',
             json.dumps(['list', 'tuple', 'string', 'array'], ensure_ascii=False),
             'D', 2, admin_id),

            ('single', 'Python中用于输出内容到控制台的函数是？',
             json.dumps(['input()', 'print()', 'output()', 'console.log()'], ensure_ascii=False),
             'B', 2, admin_id),

            ('single', '以下哪个是Python的注释符号？',
             json.dumps(['//', '/*', '#', '<!--'], ensure_ascii=False),
             'C', 2, admin_id),

            ('single', 'Python中列表的索引从几开始？',
             json.dumps(['0', '1', '-1', '任意'], ensure_ascii=False),
             'A', 2, admin_id),

            ('single', '以下哪个关键字用于定义类？',
             json.dumps(['struct', 'class', 'def', 'object'], ensure_ascii=False),
             'B', 2, admin_id),

            ('single', 'Python中哪个符号用于字符串格式化？',
             json.dumps(['$', '#', '%', '&'], ensure_ascii=False),
             'C', 2, admin_id),

            # 多选题
            ('multiple', 'Python中的可变数据类型有哪些？',
             json.dumps(['list', 'tuple', 'dict', 'set'], ensure_ascii=False),
             'A,C,D', 3, admin_id),

            ('multiple', '以下哪些是Python的循环语句？',
             json.dumps(['for', 'while', 'do-while', 'foreach'], ensure_ascii=False),
             'A,B', 3, admin_id),

            ('multiple', 'Python中常用的Web框架有哪些？',
             json.dumps(['Django', 'Flask', 'Spring', 'Express'], ensure_ascii=False),
             'A,B', 3, admin_id),

            ('multiple', '以下哪些是Python的内置数据类型？',
             json.dumps(['int', 'str', 'float', 'array'], ensure_ascii=False),
             'A,B,C', 3, admin_id),

            # 判断题
            ('judge', 'Python是解释型语言', '[]', 'True', 2, admin_id),
            ('judge', 'Python支持多继承', '[]', 'True', 2, admin_id),
            ('judge', 'Python是一种编译型语言', '[]', 'False', 2, admin_id),
            ('judge', 'Python的变量声明需要指定类型', '[]', 'False', 2, admin_id),
            ('judge', 'Python使用缩进来表示代码块', '[]', 'True', 2, admin_id),

            # 简答题
            ('essay', '请简述Python中列表和元组的区别',
             '[]', '列表是可变的，元组是不可变的；列表使用[]，元组使用()；列表功能更丰富但占用内存更多', 5, admin_id),
            ('essay', '什么是Python的装饰器？',
             '[]', '装饰器是一种在不修改原函数代码的情况下，给函数增加额外功能的方式，使用@语法糖', 5, admin_id),
            ('essay', '请解释Python中的GIL是什么',
             '[]', 'GIL是全局解释器锁，它确保任何时候只有一个线程在执行Python字节码，限制了多线程的并行执行', 5, admin_id),
        ]

        # 清空现有题目
        cursor.execute("DELETE FROM questions")

        for q in sample_questions:
            cursor.execute("""
                INSERT INTO questions (type, content, options, answer, score, created_by)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, q)

        print(f"✓ 插入了 {len(sample_questions)} 道示例题目")

        # 插入示例考试（带时间）
        from datetime import datetime, timedelta
        now = datetime.now()
        valid_from = now - timedelta(days=1)
        valid_to = now + timedelta(days=30)

        sample_exams = [
            ('Python基础考试', '测试Python基础知识，共30题', 5, 2, 5, 2, 2, 3, 2, 5, admin_id, valid_from, valid_to, 60),
            ('Python进阶考试', '测试Python高级知识，共30题', 5, 3, 5, 3, 2, 3, 2, 5, admin_id, valid_from, valid_to, 60),
        ]

        cursor.execute("DELETE FROM exams")

        for exam in sample_exams:
            cursor.execute("""
                INSERT INTO exams (title, description, single_count, multiple_count, 
                                 judge_count, essay_count, single_score, multiple_score, 
                                 judge_score, essay_score, created_by, valid_from, valid_to, duration_minutes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, exam)

        print(f"✓ 插入了 {len(sample_exams)} 个示例考试")

        conn.commit()
        print("\n✅ 初始数据插入成功！")

    except Exception as e:
        print(f"❌ 插入数据时出错: {e}")
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

def reset_database():
    """重置数据库（删除所有表后重建）"""

    response = input("\n⚠️  警告：这将删除所有数据！确定要继续吗？(yes/no): ")
    if response.lower() != 'yes':
        print("操作已取消")
        return

    conn = pymysql.connect(**DB_CONFIG, database=DATABASE_NAME)
    cursor = conn.cursor()

    try:
        # 删除所有表
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")

        tables = ['practice_records', 'exam_records', 'exam_questions', 'exams', 'questions', 'users']
        for table in tables:
            cursor.execute(f"DROP TABLE IF EXISTS {table}")
            print(f"✓ 删除表 '{table}'")

        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
        conn.commit()

        print("\n✅ 所有表已删除")

        # 重新创建表
        create_database_and_tables()

        # 重新插入数据
        insert_initial_data()

    except Exception as e:
        print(f"❌ 重置数据库时出错: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

def check_database():
    """检查数据库状态"""

    conn = pymysql.connect(**DB_CONFIG, database=DATABASE_NAME)
    cursor = conn.cursor()

    try:
        # 检查表
        cursor.execute("SHOW TABLES")
        tables = cursor.fetchall()

        print("\n📊 数据库状态检查:")
        print("-" * 40)
        print(f"数据库: {DATABASE_NAME}")
        print(f"表数量: {len(tables)}")

        table_info = {}
        for table in tables:
            table_name = table[0]
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cursor.fetchone()[0]
            table_info[table_name] = count

        for name, count in table_info.items():
            print(f"  - {name}: {count} 条记录")

        # 检查用户角色分布
        if 'users' in table_info and table_info['users'] > 0:
            cursor.execute("SELECT role, COUNT(*) FROM users GROUP BY role")
            roles = cursor.fetchall()
            print("\n用户角色分布:")
            for role, count in roles:
                print(f"  - {role}: {count} 人")

        print("-" * 40)

    except Exception as e:
        print(f"❌ 检查数据库时出错: {e}")
    finally:
        cursor.close()
        conn.close()

def get_mysql_version():
    """获取MySQL版本"""
    try:
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT VERSION()")
        version = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        return version
    except:
        return "未知"

if __name__ == '__main__':
    import sys

    print("=" * 50)
    print("在线考试系统 - 数据库初始化工具")
    print("=" * 50)

    # 显示MySQL版本
    version = get_mysql_version()
    print(f"MySQL版本: {version}")

    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == 'reset':
            reset_database()
        elif command == 'check':
            check_database()
        elif command == 'init':
            create_database_and_tables()
            insert_initial_data()
        else:
            print(f"未知命令: {command}")
            print("可用命令: init, reset, check")
    else:
        # 默认执行完整初始化
        print("\n正在初始化数据库...\n")
        try:
            create_database_and_tables()
            insert_initial_data()
            check_database()

            print("\n✨ 数据库初始化完成！")
            print("\n默认管理员账号:")
            print("  用户名: admin")
            print("  密码: admin123")
            print("\n现在可以运行 python app.py 启动考试系统了")
        except Exception as e:
            print(f"\n❌ 初始化失败: {e}")
            print("\n请检查:")
            print("1. MySQL服务是否已启动")
            print("2. 数据库用户名和密码是否正确")
            print("3. 在DB_CONFIG中修改为正确的配置")