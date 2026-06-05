from flask import Flask, render_template, request, jsonify, session, send_from_directory, redirect, url_for
import re
import json
import os
import time
from datetime import datetime, timedelta
from threading import Timer
import socket
from werkzeug.utils import secure_filename
from article_format import format_article_content, format_article_excerpt

app = Flask(__name__)

@app.template_filter('format_article')
def format_article_filter(text):
    return format_article_content(text)
app.secret_key = 'n0c_s3cr3t_k3y_2024'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'docx', 'xlsx', 'pptx', 'txt'}
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

LOG_FILE = 'logs.json'
WIKI_DATA_FILE = 'wiki_data.json'
MESSAGES_FILE = 'messages.json'
LOG_RETENTION_DAYS = 14

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def safe_load_json(path, default):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(default, f, ensure_ascii=False, indent=2)
        return default

def init_files():
    safe_load_json(LOG_FILE, [])
    safe_load_json(WIKI_DATA_FILE, {"categories": []})
    safe_load_json(MESSAGES_FILE, {"messages": []})

init_files()

ADMIN_PASSWORD = "noc_support1337"

@app.context_processor
def inject_auth():
    return {'logged_in': bool(session.get('logged_in'))}

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return '127.0.0.1'

def clean_old_logs():
    logs = safe_load_json(LOG_FILE, [])
    cutoff_date = datetime.now() - timedelta(days=LOG_RETENTION_DAYS)
    logs = [log for log in logs if datetime.fromisoformat(log['timestamp']) > cutoff_date]
    with open(LOG_FILE, 'w', encoding='utf-8') as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)

def add_log(ip, input_str, count):
    logs = safe_load_json(LOG_FILE, [])
    logs.append({
        'timestamp': datetime.now().isoformat(),
        'ip': ip,
        'input': input_str,
        'count': count
    })
    with open(LOG_FILE, 'w', encoding='utf-8') as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)

def expand_lac_tac(input_str):
    if not input_str.strip():
        return []
    tokens = [s.strip() for s in input_str.split(',')]
    result = set()
    for token in tokens:
        if '-' in token:
            try:
                start, end = map(int, token.split('-'))
                if start <= end:
                    result.update(range(start, end + 1))
            except:
                continue
        else:
            try:
                result.add(int(token))
            except:
                continue
    return sorted(list(result))

def parse_time_string(time_str):
    total_minutes = 0
    matches = re.findall(r'(\d+(?:\.\d+)?)\s*([дчм])', time_str, re.IGNORECASE)
    for value, unit in matches:
        num = float(value)
        unit = unit.lower()
        if unit == 'д':
            total_minutes += num * 24 * 60
        elif unit == 'ч':
            total_minutes += num * 60
        elif unit == 'м':
            total_minutes += num
    return total_minutes

def load_json(path):
    return safe_load_json(path, {})

def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def now_fmt():
    return datetime.now().strftime("%d.%m.%Y %H:%M")

def touch_article(article, ip, is_new=False):
    t = now_fmt()
    if is_new:
        article['created_at'] = t
        article['created_ip'] = ip
    article['updated_at'] = t
    article['updated_ip'] = ip

def normalize_article(article):
    article.setdefault('images', [article['image']] if article.get('image') else [])
    article.setdefault('files', [])
    article.setdefault('created_at', '—')
    article.setdefault('created_ip', '—')
    article.setdefault('updated_at', article.get('created_at', '—'))
    article.setdefault('updated_ip', article.get('created_ip', '—'))
    return article

def find_article(wiki_data, article_id):
    for category in wiki_data['categories']:
        for article in category['articles']:
            if article['id'] == article_id:
                return category, normalize_article(article)
    return None, None

def save_uploaded_files(file_list):
    saved = []
    for file in file_list:
        if file and file.filename != '' and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filename = f"{int(time.time())}_{filename}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            saved.append(f'uploads/{filename}')
            time.sleep(0.01)
    return saved

# === НОВАЯ ПРОВЕРКА АВТОРИЗАЦИИ ===
@app.before_request
def require_login():
    # Публичные маршруты (не требуют логина)
    public_paths = [
        '/', '/login', '/logout', '/api/login', '/api/logout', '/expand',
        '/get_logs', '/wiki', '/messages',
        '/article', '/static'
    ]
    for path in public_paths:
        if request.path.startswith(path):
            return
    # Всё остальное (админка, добавление/удаление) только после логина
    if not session.get('logged_in'):
        if request.path.startswith('/api/') or request.is_json:
            return jsonify({'error': 'Unauthorized', 'success': False}), 401
        return redirect('/login')

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json()
    if data and data.get('password') == ADMIN_PASSWORD:
        session['logged_in'] = True
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Неверный пароль'}), 401

@app.route('/logout')
def logout_page():
    session.pop('logged_in', None)
    return redirect('/')

@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.pop('logged_in', None)
    return jsonify({'success': True})

@app.route('/')
def index():
    return render_template('index.html')

def normalize_wiki_data(wiki_data):
    for category in wiki_data.get('categories', []):
        for article in category.get('articles', []):
            normalize_article(article)
    return wiki_data

def enrich_article(article):
    a = normalize_article(dict(article))
    a['excerpt_html'] = str(format_article_excerpt(a.get('content', '')))
    return a

def enrich_category(category):
    cat = dict(category)
    cat['articles'] = [enrich_article(a) for a in category.get('articles', [])]
    return cat

@app.route('/admin')
def admin_panel():
    if not session.get('logged_in'):
        return redirect('/login')
    wiki_data = normalize_wiki_data(safe_load_json(WIKI_DATA_FILE, {"categories": []}))
    messages_data = safe_load_json(MESSAGES_FILE, {"messages": []})
    return render_template('admin/dashboard.html',
                           categories=wiki_data['categories'],
                           messages=messages_data['messages'])

@app.route('/expand', methods=['POST'])
def expand_route():
    data = request.json
    input_str = data.get('input', '')
    split_columns = data.get('split_columns', True)
    expanded = expand_lac_tac(input_str)
    client_ip = request.remote_addr
    add_log(client_ip, input_str, len(expanded))

    if not split_columns or len(expanded) == 0:
        chunks = [expanded] if expanded else [[]]
    else:
        chunks = [expanded[i:i + 100] for i in range(0, len(expanded), 100)]

    return jsonify({'chunks': chunks})

@app.route('/get_logs', methods=['GET'])
def get_logs():
    logs = safe_load_json(LOG_FILE, [])
    return jsonify({'logs': logs})

@app.route('/wiki')
def wiki_index():
    wiki_data = normalize_wiki_data(safe_load_json(WIKI_DATA_FILE, {"categories": []}))
    return jsonify({'categories': [enrich_category(c) for c in wiki_data['categories']]})

@app.route('/wiki/category/<category_id>')
def wiki_category(category_id):
    wiki_data = safe_load_json(WIKI_DATA_FILE, {"categories": []})
    for category in wiki_data['categories']:
        if category['id'] == category_id:
            return jsonify(enrich_category(category))
    return jsonify({'error': 'Категория не найдена'}), 404

@app.route('/wiki/article/<article_id>')
def wiki_article(article_id):
    wiki_data = safe_load_json(WIKI_DATA_FILE, {"categories": []})
    category, article = find_article(wiki_data, article_id)
    if not article:
        return jsonify({'error': 'Статья не найдена'}), 404
    return jsonify({
        'article': article,
        'content_html': str(format_article_content(article.get('content', ''))),
        'category': {
            'id': category['id'],
            'name': category['name'],
            'description': category.get('description', ''),
            'articles': [{'id': a['id'], 'title': a['title']} for a in category['articles']]
        }
    })

@app.route('/messages')
def get_messages():
    messages = safe_load_json(MESSAGES_FILE, {"messages": []})
    return jsonify({'messages': messages['messages']})

@app.route('/article/<article_id>')
def view_article(article_id):
    wiki_data = safe_load_json(WIKI_DATA_FILE, {"categories": []})
    category, article = find_article(wiki_data, article_id)
    if not article:
        return "Статья не найдена", 404
    return render_template('article_view.html', article=article, category=category)

@app.route('/api/add_category', methods=['POST'])
def add_category():
    data = request.get_json()
    wiki_data = safe_load_json(WIKI_DATA_FILE, {"categories": []})
    new_category = {
        "id": f"category_{int(time.time())}",
        "name": data['name'],
        "description": data['description'],
        "articles": []
    }
    wiki_data['categories'].append(new_category)
    save_json(WIKI_DATA_FILE, wiki_data)
    return jsonify({'success': True, 'category': new_category})

@app.route('/api/delete_category/<category_id>', methods=['POST'])
def delete_category(category_id):
    wiki_data = safe_load_json(WIKI_DATA_FILE, {"categories": []})
    wiki_data['categories'] = [c for c in wiki_data['categories'] if c['id'] != category_id]
    save_json(WIKI_DATA_FILE, wiki_data)
    return jsonify({'success': True})

@app.route('/api/update_category/<category_id>', methods=['POST'])
def update_category(category_id):
    data = request.get_json()
    wiki_data = safe_load_json(WIKI_DATA_FILE, {"categories": []})
    for category in wiki_data['categories']:
        if category['id'] == category_id:
            category['name'] = data.get('name', category['name']).strip()
            category['description'] = data.get('description', category.get('description', '')).strip()
            save_json(WIKI_DATA_FILE, wiki_data)
            return jsonify({'success': True, 'category': category})
    return jsonify({'error': 'Категория не найдена'}), 404

@app.route('/api/delete_article/<article_id>', methods=['POST'])
def delete_article(article_id):
    wiki_data = safe_load_json(WIKI_DATA_FILE, {"categories": []})
    for category in wiki_data['categories']:
        before = len(category['articles'])
        category['articles'] = [a for a in category['articles'] if a['id'] != article_id]
        if len(category['articles']) < before:
            save_json(WIKI_DATA_FILE, wiki_data)
            return jsonify({'success': True})
    return jsonify({'error': 'Статья не найдена'}), 404

@app.route('/api/update_article/<article_id>', methods=['POST'])
def update_article(article_id):
    wiki_data = safe_load_json(WIKI_DATA_FILE, {"categories": []})
    category, article = find_article(wiki_data, article_id)
    if not article:
        return jsonify({'error': 'Статья не найдена'}), 404

    article['title'] = request.form.get('title', article['title']).strip()
    article['content'] = request.form.get('content', article['content'])

    remove_images = request.form.get('remove_images', '')
    if remove_images:
        to_remove = set(remove_images.split(','))
        article['images'] = [img for img in article.get('images', []) if img not in to_remove]

    remove_files = request.form.get('remove_files', '')
    if remove_files:
        to_remove = set(remove_files.split(','))
        article['files'] = [f for f in article.get('files', []) if f not in to_remove]

    if 'images' in request.files:
        article['images'] = article.get('images', []) + save_uploaded_files(request.files.getlist('images'))
    if 'files' in request.files:
        article['files'] = article.get('files', []) + save_uploaded_files(request.files.getlist('files'))

    touch_article(article, request.remote_addr)
    save_json(WIKI_DATA_FILE, wiki_data)
    return jsonify({'success': True, 'article': article})

@app.route('/api/add_article', methods=['POST'])
def add_article():
    category_id = request.form.get('category_id')
    title = request.form.get('title')
    content = request.form.get('content')
    wiki_data = safe_load_json(WIKI_DATA_FILE, {"categories": []})

    images = save_uploaded_files(request.files.getlist('images')) if 'images' in request.files else []
    files = save_uploaded_files(request.files.getlist('files')) if 'files' in request.files else []

    new_article = {
        "id": f"article_{int(time.time())}",
        "title": title,
        "content": content,
        "images": images,
        "files": files
    }
    touch_article(new_article, request.remote_addr, is_new=True)

    for category in wiki_data['categories']:
        if category['id'] == category_id:
            category['articles'].append(new_article)
            break

    save_json(WIKI_DATA_FILE, wiki_data)
    return jsonify({'success': True})

@app.route('/api/add_message', methods=['POST'])
def add_message():
    data = request.get_json()
    messages = safe_load_json(MESSAGES_FILE, {"messages": []})
    new_message = {
        "id": len(messages['messages']) + 1,
        "title": data['title'],
        "content": data['content'],
        "assigned_to": data['assigned_to'],
        "priority": data['priority'],
        "status": "pending",
        "created_at": datetime.now().strftime("%d.%m.%Y %H:%M")
    }
    messages['messages'].append(new_message)
    save_json(MESSAGES_FILE, messages)
    return jsonify({'success': True})

@app.route('/api/update_status/<int:msg_id>', methods=['POST'])
def api_update_status(msg_id):
    data = request.get_json()
    messages = safe_load_json(MESSAGES_FILE, {"messages": []})
    for msg in messages['messages']:
        if msg['id'] == msg_id:
            msg['status'] = data.get('status', msg['status'])
            break
    save_json(MESSAGES_FILE, messages)
    return jsonify({'success': True})

@app.route('/api/delete_message/<int:msg_id>', methods=['POST'])
def api_delete_message(msg_id):
    messages = safe_load_json(MESSAGES_FILE, {"messages": []})
    messages['messages'] = [m for m in messages['messages'] if m['id'] != msg_id]
    save_json(MESSAGES_FILE, messages)
    return jsonify({'success': True})

if __name__ == '__main__':
    Timer(0, clean_old_logs).start()
    local_ip = get_local_ip()
    print("\n" + "=" * 60)
    print("🚀 NOC Утилиты запущены!")
    print(f"🌐 Локально: http://localhost:5000")
    print(f"📡 Сеть: http://{local_ip}:5000")
    print("=" * 60 + "\n")
    app.run(host='0.0.0.0', port=5000, debug=True)