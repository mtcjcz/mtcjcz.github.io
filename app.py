from flask import Flask, render_template, request, redirect, url_for, session, jsonify, make_response
import pymysql
import json
import random
from functools import wraps
from datetime import datetime, timedelta
import sys

# 设置默认编码为UTF-8
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

app = Flask(__name__)
app.secret_key = 'your_secret_key_here_change_this'
app.config['JSON_AS_ASCII'] = False  # 让jsonify返回中文不乱码

# 数据库配置 - 使用 utf8
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',  # 修改为您的MySQL用户名
    'password': '19848377',  # 修改为您的MySQL密码
    'database': 'test3',
    'charset': 'utf8',  # 使用 utf8
    'use_unicode': True,
}

def get_db_connection():
    """获取数据库连接"""
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute("SET NAMES utf8")
    cursor.execute("SET character_set_results=utf8")
    cursor.execute("SET character_set_client=utf8")
    cursor.execute("SET character_set_connection=utf8")
    cursor.close()
    return conn


# 登录装饰器
def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('login'))
            if role and session.get('role') != role:
                return "权限不足", 403
            return f(*args, **kwargs)

        return decorated_function

    return decorator


def safe_json_parse(data, default=None):
    """安全地解析JSON数据"""
    if default is None:
        default = {}

    if not data:
        return default

    try:
        if isinstance(data, str):
            return json.loads(data)
        elif isinstance(data, (dict, list)):
            return data
        else:
            # 尝试转换为字符串再解析
            return json.loads(str(data))
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        print(f"JSON解析错误: {e}, 原始数据: {data}")
        return default


def get_username_by_id(user_id):
    """根据用户ID获取用户名"""
    if not user_id:
        return "未知"
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT username FROM users WHERE id=%s", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else "未知"


# 路由：首页重定向到登录
@app.route('/')
def index():
    return redirect(url_for('login'))


# 注册页面
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        confirm_password = request.form.get('confirm_password', '')

        # 验证密码
        if password != confirm_password:
            return "两次输入的密码不一致"

        if len(password) < 3:
            return "密码长度不能少于3位"

        # 强制角色为学生
        role = 'student'

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                "INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
                (username, password, role)
            )
            conn.commit()
            return redirect(url_for('login'))
        except pymysql.err.IntegrityError:
            return "用户名已存在"
        finally:
            conn.close()

    return render_template('register.html')


# 登录页面
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, username, role FROM users WHERE username=%s AND password=%s AND role=%s",
            (username, password, role)
        )
        user = cursor.fetchone()
        conn.close()

        if user:
            session['user_id'] = user[0]
            session['username'] = user[1]
            session['role'] = user[2]

            if role == 'student':
                return redirect(url_for('student_dashboard'))
            elif role == 'teacher':
                return redirect(url_for('teacher_dashboard'))
            else:
                return redirect(url_for('admin_dashboard'))
        else:
            return "用户名、密码或角色错误"

    return render_template('login.html')


# 登出
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# 学生控制面板
@app.route('/student_dashboard')
@login_required('student')
def student_dashboard():
    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()

    # 获取可参加的考试（检查有效时间）
    now = datetime.now()
    cursor.execute("""
        SELECT e.id, e.title, e.description, e.valid_from, e.valid_to, e.duration_minutes,
               (SELECT COUNT(*) FROM exam_records er 
                WHERE er.exam_id = e.id AND er.student_id = %s AND er.attempt_number = 1) as has_primary,
               (SELECT COUNT(*) FROM exam_records er 
                WHERE er.exam_id = e.id AND er.student_id = %s AND er.attempt_number = 2) as has_retake
        FROM exams e
        WHERE e.valid_from <= %s AND e.valid_to >= %s
    """, (user_id, user_id, now, now))
    exams = cursor.fetchall()

    # 获取成绩
    cursor.execute("""
        SELECT e.title, er.attempt_number, er.total_score, er.submit_time, er.id
        FROM exam_records er
        JOIN exams e ON er.exam_id = e.id
        WHERE er.student_id = %s
        ORDER BY er.submit_time DESC
    """, (user_id,))
    scores_data = cursor.fetchall()

    # 格式化成绩数据
    scores = []
    for s in scores_data:
        submit_time = s[3]
        if submit_time:
            submit_time = submit_time.strftime('%Y-%m-%d %H:%M')
        else:
            submit_time = '未知'
        scores.append((s[0], s[1], s[2] or 0, submit_time, s[4]))

    conn.close()

    return render_template('student_dashboard.html',
                           exams=exams,
                           scores=scores,
                           username=session['username'])


# 开始考试
@app.route('/start_exam/<int:exam_id>')
@login_required('student')
def start_exam(exam_id):
    user_id = session['user_id']
    attempt = request.args.get('attempt', 1, type=int)

    conn = get_db_connection()
    cursor = conn.cursor()

    # 检查是否还可以考试
    cursor.execute("""
        SELECT COUNT(*) FROM exam_records 
        WHERE student_id=%s AND exam_id=%s AND attempt_number=%s
    """, (user_id, exam_id, attempt))

    if cursor.fetchone()[0] > 0:
        conn.close()
        return "您已经参加过这次考试了"

    # 获取考试信息（包括时间）
    cursor.execute("""
        SELECT id, title, description, single_count, multiple_count, 
               judge_count, essay_count, single_score, multiple_score, 
               judge_score, essay_score, valid_from, valid_to, duration_minutes
        FROM exams WHERE id=%s
    """, (exam_id,))
    exam = cursor.fetchone()

    if not exam:
        conn.close()
        return "考试不存在"

    # 检查考试是否在有效期内
    now = datetime.now()
    if now < exam[11]:
        conn.close()
        return "考试尚未开始，有效开始时间：{}".format(exam[11].strftime('%Y-%m-%d %H:%M'))
    if now > exam[12]:
        conn.close()
        return "考试已过期，有效截止时间：{}".format(exam[12].strftime('%Y-%m-%d %H:%M'))

    # 按题型分别随机获取题目
    exam_questions = {
        'single': [],
        'multiple': [],
        'judge': [],
        'essay': []
    }

    # 获取单选题
    if exam[3] > 0:
        cursor.execute("""
            SELECT * FROM questions WHERE type='single' 
            ORDER BY RAND() LIMIT %s
        """, (exam[3],))
        for q in cursor.fetchall():
            exam_questions['single'].append(q)

    # 获取多选题
    if exam[4] > 0:
        cursor.execute("""
            SELECT * FROM questions WHERE type='multiple' 
            ORDER BY RAND() LIMIT %s
        """, (exam[4],))
        for q in cursor.fetchall():
            exam_questions['multiple'].append(q)

    # 获取判断题
    if exam[5] > 0:
        cursor.execute("""
            SELECT * FROM questions WHERE type='judge' 
            ORDER BY RAND() LIMIT %s
        """, (exam[5],))
        for q in cursor.fetchall():
            exam_questions['judge'].append(q)

    # 获取简答题
    if exam[6] > 0:
        cursor.execute("""
            SELECT * FROM questions WHERE type='essay' 
            ORDER BY RAND() LIMIT %s
        """, (exam[6],))
        for q in cursor.fetchall():
            exam_questions['essay'].append(q)

    conn.close()

    # 转换题目数据
    exam_data = {
        'exam_id': exam_id,
        'exam_title': exam[1],
        'attempt': attempt,
        'single_count': exam[3],
        'multiple_count': exam[4],
        'judge_count': exam[5],
        'essay_count': exam[6],
        'single_score': exam[7],
        'multiple_score': exam[8],
        'judge_score': exam[9],
        'essay_score': exam[10],
        'duration_minutes': exam[13],
        'questions': {}
    }

    for q_type in ['single', 'multiple', 'judge', 'essay']:
        questions_list = []
        for q in exam_questions[q_type]:
            # 解析选项
            options = q[3]
            if options and options != '[]':
                try:
                    options = json.loads(options)
                except:
                    if isinstance(options, str):
                        options = options.strip('[]').replace('"', '').split(',')
                    else:
                        options = []
            else:
                options = []

            questions_list.append({
                'id': q[0],
                'type': q[1],
                'content': q[2],
                'options': options,
                'answer': q[4],
                'score': q[5]
            })
        exam_data['questions'][q_type] = questions_list

    # 存储考试开始时间
    session['current_exam'] = exam_data
    session['exam_start_time'] = datetime.now().isoformat()

    return render_template('exam.html', exam=exam_data)


# 提交考试
@app.route('/submit_exam', methods=['POST'])
@login_required('student')
def submit_exam():
    if 'current_exam' not in session:
        return "没有进行中的考试"

    exam_data = session['current_exam']
    user_id = session['user_id']
    answers = {}
    total_score = 0

    conn = get_db_connection()
    cursor = conn.cursor()

    # 计算分数
    for q_type in ['single', 'multiple', 'judge', 'essay']:
        for question in exam_data['questions'][q_type]:
            q_id = question['id']
            q_type = question['type']
            q_answer = question['answer']  # 正确答案（字母，如 "A" 或 "A,B,C"）
            q_score = question['score']

            answer = request.form.get(f'question_{q_id}', '')
            answers[str(q_id)] = answer

            # 评分逻辑
            if q_type == 'single':
                # 单选题：直接比较字母
                if answer and answer.strip() == q_answer.strip():
                    total_score += q_score

            elif q_type == 'multiple':
                # 多选题：比较字母集合（忽略顺序）
                user_answers = set(answer.split(',')) if answer else set()
                user_answers = {a.strip() for a in user_answers}
                correct_answers = set(q_answer.split(',')) if q_answer else set()
                correct_answers = {a.strip() for a in correct_answers}
                if user_answers == correct_answers:
                    total_score += q_score

            elif q_type == 'judge':
                # 判断题：比较 True/False
                if answer and answer.strip() == q_answer.strip():
                    total_score += q_score

            elif q_type == 'essay':
                # 简答题：不自动给分，暂不加分
                pass

    # 将answers转换为JSON字符串存储
    answers_json = json.dumps(answers, ensure_ascii=False)

    # 保存考试记录
    cursor.execute("""
        INSERT INTO exam_records (student_id, exam_id, attempt_number, answers, total_score, submit_time)
        VALUES (%s, %s, %s, %s, %s, NOW())
    """, (user_id, exam_data['exam_id'], exam_data['attempt'],
          answers_json, total_score))

    conn.commit()
    record_id = cursor.lastrowid
    conn.close()

    session.pop('current_exam', None)
    session.pop('exam_start_time', None)

    return redirect(url_for('exam_result', record_id=record_id))


# 考试成绩页面
@app.route('/exam_result/<int:record_id>')
@login_required('student')
def exam_result(record_id):
    user_id = session['user_id']

    conn = get_db_connection()
    cursor = conn.cursor()

    # 获取考试记录和考试信息
    cursor.execute("""
        SELECT er.id, er.attempt_number, er.total_score, er.submit_time, e.title
        FROM exam_records er
        JOIN exams e ON er.exam_id = e.id
        WHERE er.id=%s AND er.student_id=%s
    """, (record_id, user_id))
    record = cursor.fetchone()

    conn.close()

    if not record:
        return "记录不存在"

    # 安全获取数据
    try:
        total_score = record[2] if record[2] is not None else 0
        if hasattr(total_score, 'strftime'):
            total_score = 0
        else:
            total_score = int(total_score)
    except:
        total_score = 0

    try:
        attempt_number = record[1] if record[1] is not None else 1
        if hasattr(attempt_number, 'strftime'):
            attempt_number = 1
        else:
            attempt_number = int(attempt_number)
    except:
        attempt_number = 1

    # 获取标题
    title = record[4] if len(record) > 4 and record[4] else '未知考试'

    # 格式化提交时间
    submit_time = record[3] if len(record) > 3 else None
    if submit_time and hasattr(submit_time, 'strftime'):
        submit_time = submit_time.strftime('%Y-%m-%d %H:%M:%S')
    else:
        submit_time = '未知'

    # 创建新的record字典
    result_record = {
        'id': record[0],
        'title': title,
        'attempt_number': attempt_number,
        'total_score': total_score,
        'submit_time': submit_time
    }

    return render_template('exam_result.html', record=result_record)


# 查看试卷
@app.route('/view_paper/<int:record_id>')
@login_required('student')
def view_paper(record_id):
    user_id = session['user_id']

    conn = get_db_connection()
    cursor = conn.cursor()

    # 获取考试记录
    cursor.execute("""
        SELECT er.*, e.title 
        FROM exam_records er
        JOIN exams e ON er.exam_id = e.id
        WHERE er.id=%s AND er.student_id=%s
    """, (record_id, user_id))
    record = cursor.fetchone()

    if not record:
        conn.close()
        return "记录不存在"

    # 解析答案
    answers_str = record[4]
    answers = {}
    if answers_str:
        try:
            if isinstance(answers_str, str):
                answers = json.loads(answers_str)
        except:
            answers = {}

    # 获取题目ID列表
    question_ids = [int(qid) for qid in answers.keys() if str(qid).isdigit()]

    # 根据题目ID获取题目详情
    questions = []
    if question_ids:
        placeholders = ','.join(['%s'] * len(question_ids))
        cursor.execute(f"""
            SELECT * FROM questions 
            WHERE id IN ({placeholders})
        """, question_ids)
        questions = cursor.fetchall()

    conn.close()

    # 构建题目列表并重新计算分数（用于验证）
    results = []
    recalculated_score = 0

    for q in questions:
        q_id = q[0]
        q_type = q[1]
        q_content = q[2]
        q_options = q[3]
        q_answer = q[4]
        q_score = q[5]
        user_answer = answers.get(str(q_id), '')

        # 解析选项
        options = q_options
        if options and options != '[]':
            try:
                options = json.loads(options)
            except:
                if isinstance(options, str):
                    options = options.strip('[]').replace('"', '').split(',')
                    options = [opt.strip() for opt in options if opt.strip()]
                else:
                    options = []
        else:
            options = []

        # 判断是否正确
        is_correct = None
        if q_type == 'single':
            if user_answer and user_answer == q_answer:
                is_correct = True
                recalculated_score += q_score
            else:
                is_correct = False
        elif q_type == 'multiple':
            user_ans_set = set(user_answer.split(',')) if user_answer else set()
            user_ans_set = {a.strip() for a in user_ans_set}
            correct_ans_set = set(q_answer.split(',')) if q_answer else set()
            correct_ans_set = {a.strip() for a in correct_ans_set}
            if user_ans_set == correct_ans_set:
                is_correct = True
                recalculated_score += q_score
            else:
                is_correct = False
        elif q_type == 'judge':
            if user_answer and user_answer == q_answer:
                is_correct = True
                recalculated_score += q_score
            else:
                is_correct = False
        elif q_type == 'essay':
            is_correct = None

        results.append({
            'id': q_id,
            'content': q_content,
            'type': q_type,
            'options': options,
            'user_answer': user_answer,
            'correct_answer': q_answer,
            'is_correct': is_correct,
            'score': q_score
        })

    # 使用数据库中存储的分数或重新计算的分数
    stored_score = record[5] if record[5] else 0
    if hasattr(stored_score, 'strftime'):
        stored_score = 0

    # 考试信息
    exam_data = {
        'title': record[8],
        'attempt': record[3] if not hasattr(record[3], 'strftime') else 1,
        'total_score': stored_score,  # 使用数据库存储的分数
        'submit_time': record[7]
    }

    # 格式化提交时间
    if exam_data['submit_time'] and hasattr(exam_data['submit_time'], 'strftime'):
        exam_data['submit_time'] = exam_data['submit_time'].strftime('%Y-%m-%d %H:%M')
    else:
        exam_data['submit_time'] = '未知'

    # 计算正确题数
    correct_count = sum(1 for r in results if r['is_correct'] is True)

    return render_template('view_paper.html',
                           exam=exam_data,
                           results=results,
                           score=stored_score,
                           correct=correct_count,
                           total=len(results))


# 练习题
# 学生练习题 - 按题型顺序显示（单选、多选、判断、简答）
@app.route('/practice')
@login_required('student')
def practice():
    conn = get_db_connection()
    cursor = conn.cursor()

    questions_list = []

    # 获取各类型题目数量
    type_limits = {
        'single': 50,
        'multiple': 20,
        'judge': 20,
        'essay': 10
    }

    for q_type, limit in type_limits.items():
        cursor.execute("SELECT COUNT(*) FROM questions WHERE type=%s", (q_type,))
        count = cursor.fetchone()[0]

        actual_limit = min(limit, count) if count > 0 else 0

        if actual_limit > 0:
            cursor.execute(f"""
                SELECT * FROM questions WHERE type=%s 
                ORDER BY RAND() 
                LIMIT %s
            """, (q_type, actual_limit))
            questions = cursor.fetchall()
            for q in questions:
                questions_list.append(q)

    conn.close()

    # 转换为字典格式
    formatted_questions = []
    for q in questions_list:
        options = q[3]
        if options and options != '[]':
            try:
                options = json.loads(options)
            except:
                if isinstance(options, str):
                    options = options.strip('[]').replace('"', '').split(',')
                    options = [opt.strip() for opt in options if opt.strip()]
                else:
                    options = []
        else:
            options = []

        formatted_questions.append({
            'id': q[0],
            'type': q[1],
            'content': q[2],
            'options': options,
            'answer': q[4],
            'score': q[5]
        })

    session['practice_questions'] = formatted_questions

    return render_template('practice.html', questions=formatted_questions)


# 提交练习题
@app.route('/submit_practice', methods=['POST'])
@login_required('student')
def submit_practice():
    user_id = session['user_id']

    practice_questions = session.get('practice_questions', [])
    if not practice_questions:
        return redirect(url_for('practice'))

    conn = get_db_connection()
    cursor = conn.cursor()

    results = []
    correct_count = 0
    total = len(practice_questions)

    for question in practice_questions:
        q_id = question['id']
        q_type = question['type']
        q_answer = question['answer']
        q_content = question['content']
        q_options = question['options']

        answer = request.form.get(f'question_{q_id}', '')

        is_correct = False
        if q_type == 'single':
            if answer and answer.strip() == q_answer.strip():
                is_correct = True
                correct_count += 1
        elif q_type == 'multiple':
            user_answers = set(answer.split(',')) if answer else set()
            user_answers = {a.strip() for a in user_answers}
            correct_answers = set(q_answer.split(',')) if q_answer else set()
            correct_answers = {a.strip() for a in correct_answers}
            if user_answers == correct_answers:
                is_correct = True
                correct_count += 1
        elif q_type == 'judge':
            if answer and answer.strip() == q_answer.strip():
                is_correct = True
                correct_count += 1
        elif q_type == 'essay':
            is_correct = None

        # 保存练习记录
        cursor.execute("""
            INSERT INTO practice_records (student_id, question_id, answer, is_correct)
            VALUES (%s, %s, %s, %s)
        """, (user_id, q_id, answer, is_correct if is_correct is not None else False))

        # 记录结果用于显示
        results.append({
            'id': q_id,
            'content': q_content,
            'type': q_type,
            'options': q_options,
            'user_answer': answer,
            'correct_answer': q_answer,
            'is_correct': is_correct
        })

    conn.commit()
    conn.close()

    # 计算得分（简答题不计入自动评分）
    essay_count = len([r for r in results if r['type'] == 'essay'])
    auto_count = total - essay_count
    auto_score = (correct_count / auto_count * 100) if auto_count > 0 else 0

    session['practice_results'] = results
    session['practice_score'] = auto_score
    session['practice_correct'] = correct_count
    session['practice_total'] = total

    return redirect(url_for('practice_result'))


# 练习题结果页面
@app.route('/practice_result')
@login_required('student')
def practice_result():
    results = session.get('practice_results', [])
    score = session.get('practice_score', 0)
    correct = session.get('practice_correct', 0)
    total = session.get('practice_total', 0)

    if not results:
        return redirect(url_for('practice'))

    return render_template('practice_result.html',
                           results=results,
                           score=score,
                           correct=correct,
                           total=total)


# 继续练习 - 重新获取新题目
@app.route('/practice_continue')
@login_required('student')
def practice_continue():
    # 清除之前的练习结果
    session.pop('practice_results', None)
    session.pop('practice_questions', None)
    session.pop('practice_score', None)

    # 重新获取新题目
    return redirect(url_for('practice'))


# 老师控制面板
@app.route('/teacher_dashboard')
@login_required('teacher')
def teacher_dashboard():
    # 获取URL参数中的消息
    success_msg = request.args.get('success_msg', '')
    error_msg = request.args.get('error_msg', '')

    user_id = session['user_id']

    conn = get_db_connection()
    cursor = conn.cursor()

    # 获取所有学生列表
    cursor.execute("""
        SELECT u.id, u.username, u.created_at,
               COUNT(DISTINCT er.id) as exam_count,
               COALESCE(AVG(er.total_score), 0) as avg_score
        FROM users u
        LEFT JOIN exam_records er ON u.id = er.student_id
        WHERE u.role = 'student'
        GROUP BY u.id, u.username, u.created_at
        ORDER BY u.id
    """)
    students_data = cursor.fetchall()

    # 格式化学生数据
    students = []
    for s in students_data:
        created_at = s[2]
        if created_at:
            created_at = created_at.strftime('%Y-%m-%d %H:%M')
        else:
            created_at = '未知'

        students.append({
            'id': s[0],
            'name': s[1],
            'created_at': created_at,
            'exam_count': s[3] or 0,
            'avg_score': round(s[4] or 0, 1)
        })

    # 获取老师创建的考试（包括时间字段）
    cursor.execute("""
        SELECT id, title, description, single_count, multiple_count, 
               judge_count, essay_count, single_score, multiple_score,
               judge_score, essay_score, created_by, created_at,
               valid_from, valid_to, duration_minutes
        FROM exams 
        WHERE created_by=%s
        ORDER BY id DESC
    """, (user_id,))
    exams_data = cursor.fetchall()

    exams = []
    for e in exams_data:
        created_at = e[12]
        if created_at:
            created_at = created_at.strftime('%Y-%m-%d %H:%M')
        else:
            created_at = '未知'
        valid_from = e[13].strftime('%Y-%m-%d %H:%M') if e[13] else '未设置'
        valid_to = e[14].strftime('%Y-%m-%d %H:%M') if e[14] else '未设置'
        exams.append({
            'id': e[0],
            'title': e[1],
            'description': e[2],
            'single_count': e[3],
            'multiple_count': e[4],
            'judge_count': e[5],
            'essay_count': e[6],
            'single_score': e[7],
            'multiple_score': e[8],
            'judge_score': e[9],
            'essay_score': e[10],
            'created_at': created_at,
            'valid_from': valid_from,
            'valid_to': valid_to,
            'duration_minutes': e[15]
        })

    # 获取老师自己的题目
    cursor.execute("""
        SELECT q.id, q.type, q.content, q.options, q.answer, q.score, q.created_at,
               u.username as creator_name
        FROM questions q
        LEFT JOIN users u ON q.created_by = u.id
        WHERE q.created_by=%s
        ORDER BY q.id DESC
    """, (user_id,))
    questions_data = cursor.fetchall()

    questions = []
    for q in questions_data:
        created_at = q[6]
        if created_at and hasattr(created_at, 'strftime'):
            created_at = created_at.strftime('%Y-%m-%d %H:%M')
        else:
            created_at = '未知'
        questions.append({
            'id': q[0],
            'type': q[1],
            'content': q[2],
            'options': q[3],
            'answer': q[4],
            'score': q[5],
            'created_at': created_at,
            'creator_name': q[7] if q[7] else '未知'
        })

    # 获取学生成绩
    cursor.execute("""
        SELECT u.username, e.title, er.attempt_number, er.total_score, 
               er.submit_time, er.id
        FROM exam_records er
        JOIN users u ON er.student_id = u.id
        JOIN exams e ON er.exam_id = e.id
        WHERE e.created_by=%s
        ORDER BY er.submit_time DESC
    """, (user_id,))
    scores_data = cursor.fetchall()

    scores = []
    for s in scores_data:
        submit_time = s[4]
        if submit_time:
            submit_time = submit_time.strftime('%Y-%m-%d %H:%M')
        else:
            submit_time = '未知'
        scores.append((s[0], s[1], s[2], s[3] or 0, submit_time, s[5]))

    conn.close()

    total_scores = len(scores)

    return render_template('teacher_dashboard.html',
                           students=students,
                           exams=exams,
                           questions=questions,
                           scores=scores,
                           total_scores=total_scores,
                           username=session['username'],
                           success_msg=success_msg,
                           error_msg=error_msg)


# 老师添加学生
@app.route('/teacher/add_student', methods=['POST'])
@login_required('teacher')
def teacher_add_student():
    username = request.form['username'].strip()
    password = request.form['password']
    role = 'student'  # 固定为学生角色

    # 验证输入
    if not username or not password:
        return redirect(url_for('teacher_dashboard', error_msg='用户名和密码不能为空'))

    if len(password) < 3:
        return redirect(url_for('teacher_dashboard', error_msg='密码长度不能少于3位'))

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 检查用户名是否已存在
        cursor.execute("SELECT id FROM users WHERE username=%s", (username,))
        if cursor.fetchone():
            return redirect(url_for('teacher_dashboard', error_msg=f'用户名 "{username}" 已存在'))

        # 插入新学生
        cursor.execute("""
            INSERT INTO users (username, password, role) VALUES (%s, %s, %s)
        """, (username, password, role))
        conn.commit()

        return redirect(url_for('teacher_dashboard', success_msg=f'成功添加学生：{username}'))

    except Exception as e:
        return redirect(url_for('teacher_dashboard', error_msg=f'添加失败：{str(e)}'))
    finally:
        conn.close()


# 删除学生（老师也可以删除学生）
@app.route('/teacher/delete_student/<int:student_id>')
@login_required('teacher')
def teacher_delete_student(student_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 检查是否是学生角色
        cursor.execute("SELECT role FROM users WHERE id=%s", (student_id,))
        result = cursor.fetchone()

        if not result or result[0] != 'student':
            return redirect(url_for('teacher_dashboard', error_msg='只能删除学生账号'))

        cursor.execute("DELETE FROM users WHERE id=%s", (student_id,))
        conn.commit()

        return redirect(url_for('teacher_dashboard', success_msg='学生删除成功'))

    except Exception as e:
        return redirect(url_for('teacher_dashboard', error_msg=f'删除失败：{str(e)}'))
    finally:
        conn.close()


# 老师查看学生所有成绩
@app.route('/teacher/view_student_scores/<int:student_id>')
@login_required('teacher')
def teacher_view_student_scores(student_id):
    user_id = session['user_id']

    conn = get_db_connection()
    cursor = conn.cursor()

    # 获取学生信息
    cursor.execute("SELECT id, username FROM users WHERE id=%s AND role='student'", (student_id,))
    student = cursor.fetchone()

    if not student:
        conn.close()
        return "学生不存在"

    # 获取该学生的所有考试成绩（只显示当前老师创建的考试）
    cursor.execute("""
        SELECT er.id, e.title, er.attempt_number, er.total_score, er.submit_time, er.answers
        FROM exam_records er
        JOIN exams e ON er.exam_id = e.id
        WHERE er.student_id=%s AND e.created_by=%s
        ORDER BY er.submit_time DESC
    """, (student_id, user_id))
    scores_data = cursor.fetchall()

    # 格式化成绩数据
    scores = []
    for s in scores_data:
        submit_time = s[4]
        if submit_time and hasattr(submit_time, 'strftime'):
            submit_time = submit_time.strftime('%Y-%m-%d %H:%M')
        else:
            submit_time = '未知'

        scores.append({
            'record_id': s[0],
            'title': s[1],
            'attempt_number': s[2],
            'total_score': s[3] if s[3] else 0,
            'submit_time': submit_time,
            'answers': s[5]
        })

    conn.close()

    return render_template('teacher_student_scores.html',
                           student=student,
                           scores=scores)


# 老师查看学生试卷详情（和学生查看试卷一样的样式）
@app.route('/teacher/view_student_paper_detail/<int:record_id>')
@login_required('teacher')
def teacher_view_student_paper_detail(record_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    # 获取考试记录和学生信息
    cursor.execute("""
        SELECT er.*, e.title, u.username
        FROM exam_records er
        JOIN exams e ON er.exam_id = e.id
        JOIN users u ON er.student_id = u.id
        WHERE er.id=%s
    """, (record_id,))
    record = cursor.fetchone()

    if not record:
        conn.close()
        return "记录不存在"

    # 检查权限
    if session['role'] == 'teacher':
        cursor.execute("SELECT created_by FROM exams WHERE id=%s", (record[2],))
        exam_creator = cursor.fetchone()
        if exam_creator[0] != session['user_id']:
            conn.close()
            return "无权限查看此试卷"

    # 解析答案
    answers_str = record[4]
    answers = {}
    if answers_str:
        try:
            if isinstance(answers_str, str):
                answers = json.loads(answers_str)
        except:
            answers = {}

    # 获取题目ID列表
    question_ids = [int(qid) for qid in answers.keys() if str(qid).isdigit()]

    # 根据题目ID获取题目详情
    questions = []
    if question_ids:
        placeholders = ','.join(['%s'] * len(question_ids))
        cursor.execute(f"""
            SELECT * FROM questions 
            WHERE id IN ({placeholders})
        """, question_ids)
        questions = cursor.fetchall()

    conn.close()

    # 构建题目列表
    results = []
    for q in questions:
        q_id = q[0]
        q_type = q[1]
        q_content = q[2]
        q_options = q[3]
        q_answer = q[4]
        user_answer = answers.get(str(q_id), '')

        # 解析选项
        options = q_options
        if options and options != '[]':
            try:
                options = json.loads(options)
            except:
                if isinstance(options, str):
                    options = options.strip('[]').replace('"', '').split(',')
                    options = [opt.strip() for opt in options if opt.strip()]
                else:
                    options = []
        else:
            options = []

        # 判断是否正确
        is_correct = None
        if q_type == 'single':
            is_correct = (user_answer == q_answer)
        elif q_type == 'multiple':
            user_ans_set = set(user_answer.split(',')) if user_answer else set()
            correct_ans_set = set(q_answer.split(',')) if q_answer else set()
            is_correct = (user_ans_set == correct_ans_set)
        elif q_type == 'judge':
            is_correct = (user_answer == q_answer)
        elif q_type == 'essay':
            is_correct = None

        results.append({
            'id': q_id,
            'content': q_content,
            'type': q_type,
            'options': options,
            'user_answer': user_answer,
            'correct_answer': q_answer,
            'is_correct': is_correct
        })

    # 考试信息
    exam_data = {
        'title': record[8],
        'attempt': record[3],
        'total_score': record[5] if record[5] else 0,
        'submit_time': record[7]
    }

    # 格式化提交时间
    if exam_data['submit_time'] and hasattr(exam_data['submit_time'], 'strftime'):
        exam_data['submit_time'] = exam_data['submit_time'].strftime('%Y-%m-%d %H:%M')
    else:
        exam_data['submit_time'] = '未知'

    return render_template('teacher_view_student_paper_detail.html',
                           exam=exam_data,
                           results=results,
                           student_name=record[9],
                           student_id=record[1])


# 添加考试页面
@app.route('/add_exam', methods=['GET', 'POST'])
@login_required('teacher')
def add_exam():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        single_count = int(request.form['single_count'])
        multiple_count = int(request.form['multiple_count'])
        judge_count = int(request.form['judge_count'])
        essay_count = int(request.form['essay_count'])
        single_score = int(request.form['single_score'])
        multiple_score = int(request.form['multiple_score'])
        judge_score = int(request.form['judge_score'])
        essay_score = int(request.form['essay_score'])
        valid_from = request.form['valid_from']
        valid_to = request.form['valid_to']
        duration_minutes = int(request.form['duration_minutes'])

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO exams (title, description, single_count, multiple_count, 
                             judge_count, essay_count, single_score, multiple_score, 
                             judge_score, essay_score, created_by, valid_from, valid_to, duration_minutes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (title, description, single_count, multiple_count, judge_count,
              essay_count, single_score, multiple_score, judge_score, essay_score,
              session['user_id'], valid_from, valid_to, duration_minutes))
        conn.commit()
        conn.close()

        return redirect(url_for('teacher_dashboard'))

    return render_template('add_edit_exam.html', exam=None)


# 编辑考试（老师）
@app.route('/edit_exam/<int:exam_id>', methods=['GET', 'POST'])
@login_required('teacher')
def edit_exam(exam_id):
    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()

    # 检查权限
    cursor.execute("SELECT * FROM exams WHERE id=%s AND created_by=%s", (exam_id, user_id))
    exam = cursor.fetchone()

    if not exam:
        conn.close()
        return "无权限编辑此考试"

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        single_count = int(request.form['single_count'])
        multiple_count = int(request.form['multiple_count'])
        judge_count = int(request.form['judge_count'])
        essay_count = int(request.form['essay_count'])
        single_score = int(request.form['single_score'])
        multiple_score = int(request.form['multiple_score'])
        judge_score = int(request.form['judge_score'])
        essay_score = int(request.form['essay_score'])
        valid_from = request.form['valid_from']
        valid_to = request.form['valid_to']
        duration_minutes = int(request.form['duration_minutes'])

        cursor.execute("""
            UPDATE exams SET title=%s, description=%s, single_count=%s, multiple_count=%s,
            judge_count=%s, essay_count=%s, single_score=%s, multiple_score=%s,
            judge_score=%s, essay_score=%s, valid_from=%s, valid_to=%s, duration_minutes=%s
            WHERE id=%s
        """, (title, description, single_count, multiple_count, judge_count,
              essay_count, single_score, multiple_score, judge_score, essay_score,
              valid_from, valid_to, duration_minutes, exam_id))
        conn.commit()
        conn.close()

        return redirect(url_for('teacher_dashboard'))

    conn.close()
    return render_template('add_edit_exam.html', exam=exam)


# 添加题目
@app.route('/add_question', methods=['GET', 'POST'])
@login_required('teacher')
def add_question():
    if request.method == 'POST':
        q_type = request.form['type']
        content = request.form['content']
        answer = request.form['answer']
        score = int(request.form['score'])

        options = request.form.get('options', '[]')

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO questions (type, content, options, answer, score, created_by)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (q_type, content, options, answer, score, session['user_id']))
        conn.commit()
        conn.close()

        return redirect(url_for('teacher_dashboard'))

    return render_template('add_edit_question.html', question=None)


# 编辑题目（老师）
@app.route('/edit_question/<int:q_id>', methods=['GET', 'POST'])
@login_required('teacher')
def edit_question(q_id):
    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM questions WHERE id=%s AND created_by=%s", (q_id, user_id))
    question = cursor.fetchone()

    if not question:
        conn.close()
        return "无权限编辑此题目"

    if request.method == 'POST':
        q_type = request.form['type']
        content = request.form['content']
        answer = request.form['answer']
        score = int(request.form['score'])
        options = request.form.get('options', '[]')

        # 确保options是有效的JSON字符串
        try:
            # 验证JSON格式
            json.loads(options)
        except:
            options = '[]'

        cursor.execute("""
            UPDATE questions SET type=%s, content=%s, options=%s, answer=%s, score=%s
            WHERE id=%s
        """, (q_type, content, options, answer, score, q_id))
        conn.commit()
        conn.close()

        return redirect(url_for('teacher_dashboard'))

    conn.close()
    return render_template('add_edit_question.html', question=question)


# 老师删除题目
@app.route('/teacher/delete_question/<int:q_id>')
@login_required('teacher')
def teacher_delete_question(q_id):
    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()

    # 检查权限
    cursor.execute("SELECT id FROM questions WHERE id=%s AND created_by=%s", (q_id, user_id))
    if not cursor.fetchone():
        conn.close()
        return redirect(url_for('teacher_dashboard', error_msg='无权限删除此题目'))

    cursor.execute("DELETE FROM questions WHERE id=%s", (q_id,))
    conn.commit()
    conn.close()

    return redirect(url_for('teacher_dashboard', success_msg='题目删除成功'))


# 老师删除考试
@app.route('/teacher/delete_exam/<int:exam_id>')
@login_required('teacher')
def teacher_delete_exam(exam_id):
    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()

    # 检查权限
    cursor.execute("SELECT id FROM exams WHERE id=%s AND created_by=%s", (exam_id, user_id))
    if not cursor.fetchone():
        conn.close()
        return redirect(url_for('teacher_dashboard', error_msg='无权限删除此考试'))

    cursor.execute("DELETE FROM exams WHERE id=%s", (exam_id,))
    conn.commit()
    conn.close()

    return redirect(url_for('teacher_dashboard', success_msg='考试删除成功'))


# 管理员控制面板
@app.route('/admin_dashboard')
@login_required('admin')
def admin_dashboard():
    conn = get_db_connection()
    cursor = conn.cursor()

    # 获取所有用户并按角色分类
    cursor.execute("""
        SELECT id, username, role, created_at
        FROM users 
        ORDER BY 
            CASE role 
                WHEN 'admin' THEN 1 
                WHEN 'teacher' THEN 2 
                WHEN 'student' THEN 3 
            END,
            id
    """)
    all_users = cursor.fetchall()

    # 分类用户并格式化日期
    students = []
    teachers = []
    admins = []

    for u in all_users:
        created_at = u[3]
        if created_at and hasattr(created_at, 'strftime'):
            created_at = created_at.strftime('%Y-%m-%d %H:%M')
        else:
            created_at = '未知'

        user_info = (u[0], u[1], u[2], created_at)

        if u[2] == 'student':
            students.append(user_info)
        elif u[2] == 'teacher':
            teachers.append(user_info)
        else:
            admins.append(user_info)

    # 获取所有考试列表（包括创建者信息）
    cursor.execute("""
        SELECT e.id, e.title, e.description, e.single_count, e.multiple_count, 
               e.judge_count, e.essay_count, e.created_by, e.created_at,
               e.valid_from, e.valid_to, e.duration_minutes,
               u.username as creator_name
        FROM exams e
        LEFT JOIN users u ON e.created_by = u.id
        ORDER BY e.id DESC
    """)
    exams_data = cursor.fetchall()

    exams = []
    for e in exams_data:
        created_at = e[8]
        if created_at and hasattr(created_at, 'strftime'):
            created_at = created_at.strftime('%Y-%m-%d %H:%M')
        else:
            created_at = '未知'
        valid_from = e[9].strftime('%Y-%m-%d %H:%M') if e[9] else '未设置'
        valid_to = e[10].strftime('%Y-%m-%d %H:%M') if e[10] else '未设置'
        exams.append({
            'id': e[0],
            'title': e[1],
            'description': e[2],
            'single_count': e[3],
            'multiple_count': e[4],
            'judge_count': e[5],
            'essay_count': e[6],
            'created_by': e[7],
            'created_at': created_at,
            'valid_from': valid_from,
            'valid_to': valid_to,
            'duration_minutes': e[11],
            'creator_name': e[12] if e[12] else '未知'
        })

    # 获取所有题目列表（包括创建者信息）
    cursor.execute("""
        SELECT q.id, q.type, q.content, q.options, q.answer, q.score, q.created_by, q.created_at,
               u.username as creator_name
        FROM questions q
        LEFT JOIN users u ON q.created_by = u.id
        ORDER BY q.id DESC
    """)
    questions_data = cursor.fetchall()

    questions = []
    for q in questions_data:
        created_at = q[7]
        if created_at and hasattr(created_at, 'strftime'):
            created_at = created_at.strftime('%Y-%m-%d %H:%M')
        else:
            created_at = '未知'
        questions.append({
            'id': q[0],
            'type': q[1],
            'content': q[2],
            'options': q[3],
            'answer': q[4],
            'score': q[5],
            'created_by': q[6],
            'created_at': created_at,
            'creator_name': q[8] if q[8] else '未知'
        })

    # 获取成绩列表
    cursor.execute("""
        SELECT u.username, e.title, er.total_score, er.submit_time, er.id
        FROM exam_records er
        JOIN users u ON er.student_id = u.id
        JOIN exams e ON er.exam_id = e.id
        ORDER BY er.submit_time DESC
        LIMIT 50
    """)
    scores_data = cursor.fetchall()

    scores = []
    for s in scores_data:
        submit_time = s[3]
        if submit_time and hasattr(submit_time, 'strftime'):
            submit_time = submit_time.strftime('%Y-%m-%d %H:%M')
        else:
            submit_time = '未知'
        scores.append((s[0], s[1], s[2] or 0, submit_time, s[4]))

    conn.close()

    return render_template('admin_dashboard.html',
                           students=students,
                           teachers=teachers,
                           admins=admins,
                           exams=exams,
                           questions=questions,
                           scores=scores,
                           username=session['username'])


# 管理员查看学生试卷
@app.route('/admin/view_student_paper/<int:record_id>')
@login_required('admin')
def admin_view_student_paper(record_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    # 获取考试记录和学生信息
    cursor.execute("""
        SELECT er.*, e.title, u.username
        FROM exam_records er
        JOIN exams e ON er.exam_id = e.id
        JOIN users u ON er.student_id = u.id
        WHERE er.id=%s
    """, (record_id,))
    record = cursor.fetchone()

    if not record:
        conn.close()
        return "记录不存在"

    # 解析答案
    answers_str = record[4]
    answers = {}
    if answers_str:
        try:
            if isinstance(answers_str, str):
                answers = json.loads(answers_str)
        except:
            answers = {}

    # 获取题目ID列表
    question_ids = [int(qid) for qid in answers.keys() if str(qid).isdigit()]

    # 根据题目ID获取题目详情
    questions = []
    if question_ids:
        placeholders = ','.join(['%s'] * len(question_ids))
        cursor.execute(f"""
            SELECT * FROM questions 
            WHERE id IN ({placeholders})
        """, question_ids)
        questions = cursor.fetchall()

    conn.close()

    # 构建题目列表
    results = []
    for q in questions:
        q_id = q[0]
        q_type = q[1]
        q_content = q[2]
        q_options = q[3]
        q_answer = q[4]
        user_answer = answers.get(str(q_id), '')

        # 解析选项
        options = q_options
        if options and options != '[]':
            try:
                options = json.loads(options)
            except:
                if isinstance(options, str):
                    options = options.strip('[]').replace('"', '').split(',')
                    options = [opt.strip() for opt in options if opt.strip()]
                else:
                    options = []
        else:
            options = []

        # 判断是否正确
        is_correct = None
        if q_type == 'single':
            is_correct = (user_answer == q_answer)
        elif q_type == 'multiple':
            user_ans_set = set(user_answer.split(',')) if user_answer else set()
            user_ans_set = {a.strip() for a in user_ans_set}
            correct_ans_set = set(q_answer.split(',')) if q_answer else set()
            correct_ans_set = {a.strip() for a in correct_ans_set}
            is_correct = (user_ans_set == correct_ans_set)
        elif q_type == 'judge':
            is_correct = (user_answer == q_answer)
        elif q_type == 'essay':
            is_correct = None

        results.append({
            'id': q_id,
            'content': q_content,
            'type': q_type,
            'options': options,
            'user_answer': user_answer,
            'correct_answer': q_answer,
            'is_correct': is_correct
        })

    # 考试信息
    exam_data = {
        'title': record[8],
        'attempt': record[3],
        'total_score': record[5] if record[5] else 0,
        'submit_time': record[7]
    }

    # 格式化提交时间
    if exam_data['submit_time'] and hasattr(exam_data['submit_time'], 'strftime'):
        exam_data['submit_time'] = exam_data['submit_time'].strftime('%Y-%m-%d %H:%M')
    else:
        exam_data['submit_time'] = '未知'

    return render_template('admin_view_student_paper.html',
                           exam=exam_data,
                           results=results,
                           student_name=record[9],
                           student_id=record[1])


# 管理员删除用户
@app.route('/admin/delete_user/<int:user_id>')
@login_required('admin')
def delete_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE id=%s AND role != 'admin'", (user_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin_dashboard'))


# 管理员删除考试
@app.route('/admin/delete_exam/<int:exam_id>')
@login_required('admin')
def delete_exam(exam_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM exams WHERE id=%s", (exam_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin_dashboard'))


# 管理员删除题目
@app.route('/admin/delete_question/<int:q_id>')
@login_required('admin')
def delete_question(q_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM questions WHERE id=%s", (q_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin_dashboard'))


# 管理员编辑任意考试
@app.route('/admin/edit_exam/<int:exam_id>', methods=['GET', 'POST'])
@login_required('admin')
def admin_edit_exam(exam_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        single_count = int(request.form['single_count'])
        multiple_count = int(request.form['multiple_count'])
        judge_count = int(request.form['judge_count'])
        essay_count = int(request.form['essay_count'])
        single_score = int(request.form['single_score'])
        multiple_score = int(request.form['multiple_score'])
        judge_score = int(request.form['judge_score'])
        essay_score = int(request.form['essay_score'])
        valid_from = request.form['valid_from']
        valid_to = request.form['valid_to']
        duration_minutes = int(request.form['duration_minutes'])

        cursor.execute("""
            UPDATE exams SET title=%s, description=%s, single_count=%s, multiple_count=%s,
            judge_count=%s, essay_count=%s, single_score=%s, multiple_score=%s,
            judge_score=%s, essay_score=%s, valid_from=%s, valid_to=%s, duration_minutes=%s
            WHERE id=%s
        """, (title, description, single_count, multiple_count, judge_count,
              essay_count, single_score, multiple_score, judge_score, essay_score,
              valid_from, valid_to, duration_minutes, exam_id))
        conn.commit()
        conn.close()
        return redirect(url_for('admin_dashboard'))

    cursor.execute("SELECT * FROM exams WHERE id=%s", (exam_id,))
    exam = cursor.fetchone()
    conn.close()

    return render_template('add_edit_exam.html', exam=exam)


# 管理员编辑任意题目
@app.route('/admin/edit_question/<int:q_id>', methods=['GET', 'POST'])
@login_required('admin')
def admin_edit_question(q_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        q_type = request.form['type']
        content = request.form['content']
        answer = request.form['answer']
        score = int(request.form['score'])
        options = request.form.get('options', '[]')

        # 确保options是有效的JSON字符串
        try:
            json.loads(options)
        except:
            options = '[]'

        cursor.execute("""
            UPDATE questions SET type=%s, content=%s, options=%s, answer=%s, score=%s
            WHERE id=%s
        """, (q_type, content, options, answer, score, q_id))
        conn.commit()
        conn.close()
        return redirect(url_for('admin_dashboard'))

    cursor.execute("SELECT * FROM questions WHERE id=%s", (q_id,))
    question = cursor.fetchone()
    conn.close()

    return render_template('add_edit_question.html', question=question)


@app.template_filter('parse_options')
def parse_options(options_str):
    """解析JSON格式的选项字符串"""
    if not options_str or options_str == '[]':
        return []
    try:
        return json.loads(options_str)
    except:
        return []


@app.template_filter('format_answer')
def format_answer(answer, q_type):
    """格式化答案显示"""
    if q_type == 'multiple' and answer:
        try:
            # 尝试解析JSON数组
            if answer.startswith('['):
                answers = json.loads(answer)
                return ', '.join(answers)
        except:
            pass
    return answer


# 管理员添加用户
@app.route('/admin/add_user', methods=['POST'])
@login_required('admin')
def admin_add_user():
    username = request.form['username'].strip()
    password = request.form['password']
    role = request.form['role']

    # 验证输入
    if not username or not password:
        return redirect(url_for('admin_dashboard', error_msg='用户名和密码不能为空'))

    if len(password) < 3:
        return redirect(url_for('admin_dashboard', error_msg='密码长度不能少于3位'))

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 检查用户名是否已存在
        cursor.execute("SELECT id FROM users WHERE username=%s", (username,))
        if cursor.fetchone():
            return redirect(url_for('admin_dashboard', error_msg=f'用户名 "{username}" 已存在'))

        # 直接插入新用户
        cursor.execute("""
            INSERT INTO users (username, password, role) VALUES (%s, %s, %s)
        """, (username, password, role))
        conn.commit()

        role_name = '学生' if role == 'student' else '老师'
        return redirect(url_for('admin_dashboard', success_msg=f'成功添加{role_name}：{username}'))

    except Exception as e:
        return redirect(url_for('admin_dashboard', error_msg=f'添加失败：{str(e)}'))
    finally:
        conn.close()


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)