import requests
import time
import random
import json
import smtplib
import os
import threading
from email.message import EmailMessage
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

# ================= CONFIGURATION =================
ADMIN_ID = 7684684739
CHANNEL_USERNAME = "@wabanreport"
CHANNEL_LINK = "https://t.me/+tmrGH8UwjUw4ODY0"
PORT = int(os.environ.get('PORT', 8080))

def load_env():
    if not os.path.exists('.env'):
        return
    with open('.env', 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                key, val = line.split('=', 1)
                os.environ[key] = val

load_env()

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
if not TELEGRAM_TOKEN:
    print("ERREUR: TELEGRAM_TOKEN non défini")
    exit(1)

SMTP_ACCOUNTS_FILE = "smtp_accounts.json"

def load_smtp_accounts():
    accounts = []
    env_accounts = os.getenv('SMTP_ACCOUNTS', '[]')
    try:
        env_accounts = json.loads(env_accounts)
        accounts.extend(env_accounts)
        print(f"✅ Chargé {len(env_accounts)} compte(s) depuis .env")
    except:
        print("⚠️ SMTP_ACCOUNTS invalide dans .env")
    
    if os.path.exists(SMTP_ACCOUNTS_FILE):
        with open(SMTP_ACCOUNTS_FILE, 'r') as f:
            json_accounts = json.load(f)
            accounts.extend(json_accounts)
            print(f"✅ Chargé {len(json_accounts)} compte(s) depuis {SMTP_ACCOUNTS_FILE}")
    
    seen = set()
    unique = []
    for acc in accounts:
        email = acc.get('email')
        if email and email not in seen:
            seen.add(email)
            unique.append(acc)
    return unique

def save_smtp_accounts(accounts):
    env_accounts = []
    try:
        env_accounts = json.loads(os.getenv('SMTP_ACCOUNTS', '[]'))
        env_emails = {acc['email'] for acc in env_accounts if 'email' in acc}
    except:
        env_emails = set()
    
    admin_accounts = [acc for acc in accounts if acc.get('email') not in env_emails]
    with open(SMTP_ACCOUNTS_FILE, 'w') as f:
        json.dump(admin_accounts, f, indent=2)

def load_recipients():
    if os.path.exists("recipients.json"):
        with open("recipients.json", 'r') as f:
            return json.load(f)
    return ["support@support.whatsapp.com", "abuse@whatsapp.com"]

def save_recipients(recipients):
    with open("recipients.json", 'w') as f:
        json.dump(recipients, f, indent=2)

SMTP_ACCOUNTS = load_smtp_accounts()
WHATSAPP_RECIPIENTS = load_recipients()

MIN_REPORTS = 1
MAX_REPORTS = 3
EMAIL_DELAY = float(os.getenv('EMAIL_DELAY', '2.0'))
MAX_REPORTS_PER_HOUR = 10

# ================= TEST SMTP CORRIGÉ (PORT 587 + STARTTLS) =================
def test_smtp_connection():
    if not SMTP_ACCOUNTS:
        print("⚠️ Aucun compte SMTP à tester")
        return
    print("🔍 Test de connexion SMTP (port 587, STARTTLS) avec le premier compte...")
    acc = SMTP_ACCOUNTS[0]
    try:
        with smtplib.SMTP('smtp.gmail.com', 587, timeout=15) as server:
            server.starttls()
            server.login(acc['email'], acc['password'])
            print(f"✅ Connexion SMTP réussie avec {acc['email']}")
    except Exception as e:
        print(f"❌ Échec connexion SMTP avec {acc['email']}: {e}")

test_smtp_connection()

# ================= VÉRIFICATION MEMBRE CANAL =================
def check_membership(user_id):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getChatMember"
    params = {'chat_id': CHANNEL_USERNAME, 'user_id': user_id}
    try:
        resp = requests.get(url, params=params, timeout=10).json()
        if resp.get('ok'):
            status = resp['result'].get('status')
            return status in ['member', 'administrator', 'creator']
        return False
    except Exception as e:
        print(f"Erreur vérification: {e}")
        return False

def is_member(user_id):
    return check_membership(user_id)

def send_join_required(chat_id):
    keyboard = {
        'inline_keyboard': [
            [{'text': '📢 Rejoindre le canal', 'url': CHANNEL_LINK}],
            [{'text': '✅ J\'ai rejoint', 'callback_data': 'verify_join'}]
        ]
    }
    send_message(chat_id, 
        f"🚨 *Accès restreint*\n\n"
        f"Pour utiliser ce bot, vous devez d'abord rejoindre notre canal.\n\n"
        f"👥 Canal: {CHANNEL_USERNAME}\n\n"
        f"Rejoignez et cliquez sur *'J\\'ai rejoint'* pour continuer.\n\n"
        f"👤 Dev: @bestiemondie426",
        parse_mode='Markdown',
        reply_markup=keyboard)

# ================= NOMS D'EXPÉDITEURS =================
FIRST_NAMES = ["James", "Mary", "John", "Patricia", "Robert", "Jennifer", "Michael", "Linda", "William", "Elizabeth", "David", "Barbara", "Richard", "Susan", "Joseph", "Jessica", "Thomas", "Sarah", "Charles", "Karen", "Christopher", "Nancy", "Daniel", "Lisa", "Matthew", "Betty", "Anthony", "Margaret", "Mark", "Sandra", "Donald", "Ashley", "Steven", "Kimberly", "Paul", "Emily", "Andrew", "Donna", "Kenneth", "Michelle", "Joshua", "Dorothy", "George", "Carol", "Kevin", "Amanda", "Brian", "Melissa", "Edward", "Deborah", "Ronald", "Stephanie", "Timothy", "Rebecca", "Jason", "Sharon", "Jeffrey", "Laura", "Ryan", "Cynthia", "Jacob", "Kathleen", "Gary", "Amy", "Nicholas", "Shirley", "Eric", "Angela", "Jonathan", "Helen", "Stephen", "Anna", "Larry", "Brenda", "Justin", "Pamela", "Scott", "Nicole", "Brandon", "Emma", "Benjamin", "Samantha", "Samuel", "Katherine", "Gregory", "Christine", "Alexander", "Debra", "Frank", "Rachel", "Patrick", "Catherine", "Raymond", "Carolyn", "Jack", "Janet", "Dennis", "Ruth", "Jerry", "Maria", "Tyler", "Heather", "Aaron", "Diane", "Jose", "Virginia", "Adam", "Julie"]

LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson", "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker", "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores", "Green", "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell", "Mitchell", "Carter", "Roberts", "Gomez", "Phillips", "Evans", "Turner", "Diaz", "Parker", "Cruz", "Edwards", "Collins", "Reyes", "Stewart", "Morris", "Morales", "Murphy", "Cook", "Rogers", "Gutierrez", "Ortiz", "Morgan", "Cooper", "Peterson", "Bailey", "Reed", "Kelly", "Howard", "Ramos", "Kim", "Cox", "Ward", "Richardson", "Watson", "Brooks", "Chavez", "Wood", "James", "Bennett", "Gray", "Mendoza", "Ruiz", "Hughes", "Price", "Alvarez", "Castillo", "Sanders", "Patel", "Myers", "Long", "Ross", "Foster", "Jimenez"]

def random_sender_name():
    return f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"

# ================= GÉNÉRATION DE RAPPORT =================
def generate_detailed_report(number, category, report_index=1):
    incidents = [
        {"title": "Spam and Phishing", "desc": f"Unsolicited messages from {number} promoting fake investments with phishing links.", "evidence": "Screenshots attached.", "action": "Permanently ban this number."},
        {"title": "Harassment and Threats", "desc": f"Since {datetime.now().strftime('%B %d')}, {number} has been sending abusive messages including death threats.", "evidence": "Chat logs available.", "action": "Suspend account and preserve logs."},
        {"title": "Impersonation and Fraud", "desc": f"The account {number} is impersonating my colleague using stolen photos, asking for money.", "evidence": "Screenshots of fake profile.", "action": "Block the account immediately."},
        {"title": "Illegal Content", "desc": f"{number} is sharing explicit adult content in a group that includes minors.", "evidence": "Screenshots of messages.", "action": "Remove the account."},
        {"title": "Privacy Violation", "desc": f"The user posted my private phone number on a public WhatsApp group without consent.", "evidence": "Screenshots available.", "action": "Remove the content."}
    ]
    incident = random.choice(incidents)
    body = f"""URGENT: WhatsApp Terms of Service Violation - {incident['title']}

Number: {number}
Category: {category}
Report ID: RPT-{random.randint(10000,99999)}-{report_index}
Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Description:
{incident['desc']}

Evidence:
{incident['evidence']}

Action requested:
{incident['action']}

Sincerely,
[Concerned User]"""
    return body

def generate_subject(number, category):
    return random.choice([f"Violation - {number} ({category})", f"Complaint: {category} from {number}", f"URGENT: {category} - {number}"])

# ================= ENVOI SMTP CORRIGÉ (PORT 587 + STARTTLS) =================
def send_email(account, to, subject, body, sender_name):
    try:
        msg = EmailMessage()
        msg.set_content(body)
        msg['Subject'] = subject
        msg['From'] = f'"{sender_name}" <{account["email"]}>'
        msg['To'] = to
        # Utilisation du port 587 avec STARTTLS (plus fiable sur Render)
        with smtplib.SMTP('smtp.gmail.com', 587, timeout=30) as server:
            server.starttls()
            server.login(account['email'], account['password'])
            server.send_message(msg)
        print(f"✅ Email envoyé par {account['email']} vers {to}")
        return True, None
    except Exception as e:
        err_msg = str(e)
        print(f"❌ Erreur SMTP avec {account['email']}: {err_msg}")
        return False, err_msg

def send_single_report(chat_id, msg_id, number, category, recipient):
    if not SMTP_ACCOUNTS:
        edit_message(chat_id, msg_id, "❌ Aucun compte SMTP configuré.")
        return 0, 1
    account = random.choice(SMTP_ACCOUNTS)
    sender = random_sender_name()
    ok, err = send_email(account, recipient, generate_subject(number, category), generate_detailed_report(number, category), sender)
    if ok:
        edit_message(chat_id, msg_id, f"✅ Envoi réussi !\n\n📊 Rapports: 1\n✅ Succès: 1\n❌ Échecs: 0")
    else:
        edit_message(chat_id, msg_id, f"❌ Échec de l'envoi\n\nErreur: {err}\nVérifiez les logs du bot.")
        send_message(ADMIN_ID, f"Erreur SMTP pour {recipient} depuis {account['email']}:\n{err}")
    return 1 if ok else 0, 0 if ok else 1

def send_multiple_reports(chat_id, msg_id, number, category, quantity, recipient):
    if not SMTP_ACCOUNTS:
        edit_message(chat_id, msg_id, "❌ Aucun compte SMTP configuré.")
        return 0, quantity
    success, fail = 0, 0
    for i in range(quantity):
        account = random.choice(SMTP_ACCOUNTS)
        sender = random_sender_name()
        ok, err = send_email(account, recipient, generate_subject(number, category), generate_detailed_report(number, category, i+1), sender)
        if ok:
            success += 1
        else:
            fail += 1
            send_message(ADMIN_ID, f"Erreur rapport {i+1}/{quantity}: {err} (compte {account['email']})")
        edit_message(chat_id, msg_id, f"📤 Progression: {i+1}/{quantity} | ✅ {success} | ❌ {fail}")
        time.sleep(EMAIL_DELAY)
    
    summary = f"✅ Envoi terminé !\n\n📊 Rapports: {quantity}\n✅ Succès: {success}\n❌ Échecs: {fail}"
    edit_message(chat_id, msg_id, summary)
    return success, fail

# ================= FONCTIONS TELEGRAM =================
def send_message(chat_id, text, reply_markup=None, parse_mode=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {'chat_id': chat_id, 'text': text}
    if reply_markup:
        payload['reply_markup'] = json.dumps(reply_markup)
    if parse_mode:
        payload['parse_mode'] = parse_mode
    requests.post(url, json=payload, timeout=10)

def edit_message(chat_id, msg_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/editMessageText"
    requests.post(url, json={'chat_id': chat_id, 'message_id': msg_id, 'text': text}, timeout=10)

def answer_callback(callback_id):
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery", json={'callback_query_id': callback_id})

def send_message_and_get_id(chat_id, text):
    resp = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={'chat_id': chat_id, 'text': text}, timeout=10).json()
    return resp.get('result') if resp.get('ok') else None

user_sessions = {}
user_stats = {}

def check_rate_limit(user_id):
    now = time.time()
    if user_id not in user_stats:
        user_stats[user_id] = {'count': 0, 'last_reset': now}
    stats = user_stats[user_id]
    if now - stats['last_reset'] > 3600:
        stats['count'] = 0
        stats['last_reset'] = now
    return stats['count'] < MAX_REPORTS_PER_HOUR

def update_rate_limit(user_id, delta):
    stats = user_stats.setdefault(user_id, {'count': 0, 'last_reset': time.time()})
    stats['count'] += delta

def is_valid_number(num):
    return num.startswith('+') and num[1:].replace(' ', '').isdigit() and len(num) >= 8

def is_admin(user_id):
    return user_id == ADMIN_ID

def admin_panel(chat_id):
    keyboard = {'inline_keyboard': [
        [{'text': '➕ Ajouter SMTP', 'callback_data': 'admin_add_smtp'}],
        [{'text': '➖ Supprimer SMTP', 'callback_data': 'admin_del_smtp'}],
        [{'text': '📋 Lister SMTP', 'callback_data': 'admin_list_smtp'}],
        [{'text': '📨 Ajouter destinataire', 'callback_data': 'admin_add_recipient'}],
        [{'text': '🗑 Supprimer destinataire', 'callback_data': 'admin_del_recipient'}],
        [{'text': '📋 Lister destinataires', 'callback_data': 'admin_list_recipients'}],
        [{'text': '📊 Stats bot', 'callback_data': 'admin_stats'}]
    ]}
    send_message(chat_id, "🔧 Panneau d'administration", reply_markup=keyboard)

def add_smtp_account(chat_id, email, password):
    global SMTP_ACCOUNTS
    if any(acc['email'] == email for acc in SMTP_ACCOUNTS):
        send_message(chat_id, f"❌ {email} existe déjà.")
        return
    SMTP_ACCOUNTS.append({"email": email, "password": password})
    save_smtp_accounts(SMTP_ACCOUNTS)
    send_message(chat_id, f"✅ Compte SMTP ajouté: {email}")
    # Test de connexion avec port 587 + STARTTLS
    try:
        with smtplib.SMTP('smtp.gmail.com', 587, timeout=15) as server:
            server.starttls()
            server.login(email, password)
        send_message(chat_id, f"✅ Test de connexion réussi avec {email}")
    except Exception as e:
        send_message(chat_id, f"⚠️ Le compte {email} a été ajouté mais la connexion SMTP a échoué: {e}")

def remove_smtp_account(chat_id, email):
    global SMTP_ACCOUNTS
    SMTP_ACCOUNTS = [acc for acc in SMTP_ACCOUNTS if acc['email'] != email]
    save_smtp_accounts(SMTP_ACCOUNTS)
    send_message(chat_id, f"🗑 Compte SMTP supprimé: {email}")

def list_smtp_accounts(chat_id):
    if not SMTP_ACCOUNTS:
        send_message(chat_id, "Aucun compte SMTP.")
        return
    msg = "📧 Comptes SMTP:\n"
    for i, acc in enumerate(SMTP_ACCOUNTS, 1):
        msg += f"{i}. {acc['email']}\n"
    send_message(chat_id, msg)

def add_recipient(chat_id, email):
    global WHATSAPP_RECIPIENTS
    if email not in WHATSAPP_RECIPIENTS:
        WHATSAPP_RECIPIENTS.append(email)
        save_recipients(WHATSAPP_RECIPIENTS)
        send_message(chat_id, f"✅ Destinataire ajouté: {email}")
    else:
        send_message(chat_id, "❌ Existe déjà.")

def remove_recipient(chat_id, email):
    global WHATSAPP_RECIPIENTS
    if email in WHATSAPP_RECIPIENTS:
        WHATSAPP_RECIPIENTS.remove(email)
        save_recipients(WHATSAPP_RECIPIENTS)
        send_message(chat_id, f"🗑 Destinataire supprimé: {email}")
    else:
        send_message(chat_id, "❌ Non trouvé.")

def list_recipients(chat_id):
    if not WHATSAPP_RECIPIENTS:
        send_message(chat_id, "Aucun destinataire.")
        return
    msg = "📨 Destinataires WhatsApp:\n"
    for i, rec in enumerate(WHATSAPP_RECIPIENTS, 1):
        msg += f"{i}. {rec}\n"
    send_message(chat_id, msg)

def stats_admin(chat_id):
    send_message(chat_id, f"📊 Statistiques:\n\nComptes SMTP: {len(SMTP_ACCOUNTS)}\nDestinataires: {len(WHATSAPP_RECIPIENTS)}\nLimite rapports/heure: {MAX_REPORTS_PER_HOUR}")

# ================= SERVEUR HTTP POUR RENDER =================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/' or self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Bot is running')
        else:
            self.send_response(404)
            self.end_headers()
    def log_message(self, format, *args):
        pass

def run_http_server():
    server = HTTPServer(('0.0.0.0', PORT), HealthHandler)
    print(f"✅ Serveur HTTP démarré sur le port {PORT}")
    server.serve_forever()

# ================= COMMANDES =================
def handle_command(chat_id, user_id, cmd):
    if cmd not in ['/start', '/admin']:
        if not is_member(user_id):
            send_join_required(chat_id)
            return
    
    if cmd == '/start':
        user_sessions.pop(user_id, None)
        if is_member(user_id):
            send_message(chat_id, "🚀 WhatsApp Reporter Bot\n\n/report - Signalement manuel\n/autoreport - Signalement automatique\n/stats - Votre quota")
        else:
            send_join_required(chat_id)
    
    elif cmd == '/stats':
        if not is_member(user_id):
            send_join_required(chat_id)
            return
        stats = user_stats.get(user_id, {'count': 0})
        remaining = max(0, MAX_REPORTS_PER_HOUR - stats['count'])
        send_message(chat_id, f"📊 Votre activité:\n\nRapports envoyés cette heure: {stats['count']}\nRapports restants: {remaining}")
    
    elif cmd == '/admin':
        if is_admin(user_id):
            admin_panel(chat_id)
        else:
            send_message(chat_id, "⛔ Accès refusé.")
    
    elif cmd == '/report':
        if not is_member(user_id):
            send_join_required(chat_id)
            return
        if not check_rate_limit(user_id):
            send_message(chat_id, "⏰ Limite horaire atteinte.")
            return
        user_sessions[user_id] = {'step': 'report_number', 'data': {}}
        send_message(chat_id, "📱 Envoyez le numéro WhatsApp avec indicatif: +243812345678")
    
    elif cmd == '/autoreport':
        if not is_member(user_id):
            send_join_required(chat_id)
            return
        if not check_rate_limit(user_id):
            send_message(chat_id, "⏰ Limite horaire atteinte.")
            return
        user_sessions[user_id] = {'step': 'autoreport_number', 'data': {}}
        send_message(chat_id, "📱 Envoyez le numéro WhatsApp avec indicatif:")

def handle_text(chat_id, user_id, text):
    session = user_sessions.get(user_id)
    if not session:
        send_message(chat_id, "Utilisez /start d'abord")
        return
    step, data = session['step'], session['data']

    if step == 'report_number' and is_valid_number(text):
        data['number'] = text
        session['step'] = 'report_category'
        cats = ["Spam", "Harassment", "Fake Account", "Impersonation", "Illegal Activities", "Privacy Violation", "Threats", "Scam", "Abusive Content", "Other"]
        keyboard = {'inline_keyboard': [[{'text': c, 'callback_data': f'cat_{i}'}] for i, c in enumerate(cats)]}
        send_message(chat_id, "📂 Choisissez la catégorie:", reply_markup=keyboard)

    elif step == 'autoreport_number' and is_valid_number(text):
        data['number'] = text
        cats = ["Spam", "Harassment", "Fake Account", "Impersonation", "Illegal Activities", "Privacy Violation", "Threats", "Scam", "Abusive Content", "Other"]
        data['category'] = random.choice(cats)
        data['quantity'] = 1
        session['step'] = 'autoreport_confirm'
        send_message(chat_id, f"Numéro: {text}\nCatégorie: {data['category']}\nConfirmer ? (yes/no)")

    elif step == 'autoreport_confirm' and text.lower() in ('yes', 'y'):
        recipient = random.choice(WHATSAPP_RECIPIENTS)
        msg = send_message_and_get_id(chat_id, f"📧 Envoi en cours...")
        if msg:
            ok, fail = send_single_report(chat_id, msg['message_id'], data['number'], data['category'], recipient)
            update_rate_limit(user_id, 1)
        del user_sessions[user_id]

    elif step == 'report_quantity':
        try:
            qty = int(text)
            if 1 <= qty <= 3:
                recipient = random.choice(WHATSAPP_RECIPIENTS)
                msg = send_message_and_get_id(chat_id, f"📧 Envoi de {qty} rapport(s)...")
                if msg:
                    success, fail = send_multiple_reports(chat_id, msg['message_id'], data['number'], data['category'], qty, recipient)
                    update_rate_limit(user_id, qty)
                del user_sessions[user_id]
            else:
                send_message(chat_id, "❌ Entrez un nombre entre 1 et 3.")
        except:
            send_message(chat_id, "❌ Entrez un nombre valide.")

    elif step == 'admin_add_smtp':
        data['admin_email'] = text
        session['step'] = 'admin_add_smtp_pass'
        send_message(chat_id, "🔑 Envoyez le mot de passe d'application:")

    elif step == 'admin_add_smtp_pass':
        add_smtp_account(chat_id, data.get('admin_email'), text)
        del user_sessions[user_id]

    elif step == 'admin_add_recipient':
        add_recipient(chat_id, text)
        del user_sessions[user_id]

def handle_callback(callback):
    user_id = callback['from']['id']
    chat_id = callback['message']['chat']['id']
    msg_id = callback['message']['message_id']
    data = callback['data']
    answer_callback(callback['id'])

    if data == 'verify_join':
        if is_member(user_id):
            edit_message(chat_id, msg_id, "✅ Vérification réussie ! Vous pouvez maintenant utiliser le bot.\n\n/report - Signalement\n/autoreport - Mode auto\n/stats - Votre quota")
        else:
            edit_message(chat_id, msg_id, f"❌ Vous n'avez pas encore rejoint le canal {CHANNEL_USERNAME}.\n\nRejoignez-le puis cliquez sur 'J\\'ai rejoint'.")
        return

    if data.startswith('cat_'):
        session = user_sessions.get(user_id)
        if session:
            idx = int(data.split('_')[1])
            cats = ["Spam", "Harassment", "Fake Account", "Impersonation", "Illegal Activities", "Privacy Violation", "Threats", "Scam", "Abusive Content", "Other"]
            session['data']['category'] = cats[idx]
            session['step'] = 'report_quantity'
            edit_message(chat_id, msg_id, f"Catégorie: {cats[idx]}\n\nQuantité (1-3):")
        return

    if not is_admin(user_id):
        return

    if data == 'admin_add_smtp':
        user_sessions[user_id] = {'step': 'admin_add_smtp', 'data': {}}
        edit_message(chat_id, msg_id, "📧 Envoyez l'adresse email:")
    elif data == 'admin_del_smtp':
        if not SMTP_ACCOUNTS:
            edit_message(chat_id, msg_id, "Aucun compte.")
            return
        env_accounts = []
        try:
            env_accounts = json.loads(os.getenv('SMTP_ACCOUNTS', '[]'))
            env_emails = {acc['email'] for acc in env_accounts}
        except:
            env_emails = set()
        admin_accounts = [acc for acc in SMTP_ACCOUNTS if acc['email'] not in env_emails]
        if not admin_accounts:
            edit_message(chat_id, msg_id, "Aucun compte admin à supprimer (ceux du .env sont protégés).")
            return
        keyboard = {'inline_keyboard': [[{'text': acc['email'], 'callback_data': f'del_{acc["email"]}'}] for acc in admin_accounts]}
        edit_message(chat_id, msg_id, "Choisir le compte à supprimer:", reply_markup=keyboard)
    elif data.startswith('del_'):
        email = data[4:]
        remove_smtp_account(chat_id, email)
        edit_message(chat_id, msg_id, f"✅ Supprimé: {email}")
    elif data == 'admin_list_smtp':
        list_smtp_accounts(chat_id)
    elif data == 'admin_add_recipient':
        user_sessions[user_id] = {'step': 'admin_add_recipient', 'data': {}}
        edit_message(chat_id, msg_id, "📧 Envoyez l'email destinataire:")
    elif data == 'admin_del_recipient':
        if not WHATSAPP_RECIPIENTS:
            edit_message(chat_id, msg_id, "Aucun destinataire.")
            return
        keyboard = {'inline_keyboard': [[{'text': r, 'callback_data': f'delrec_{r}'}] for r in WHATSAPP_RECIPIENTS]}
        edit_message(chat_id, msg_id, "Choisir le destinataire à supprimer:", reply_markup=keyboard)
    elif data.startswith('delrec_'):
        email = data[7:]
        remove_recipient(chat_id, email)
        edit_message(chat_id, msg_id, f"✅ Supprimé: {email}")
    elif data == 'admin_list_recipients':
        list_recipients(chat_id)
    elif data == 'admin_stats':
        stats_admin(chat_id)

# ================= MAIN =================
def main():
    http_thread = threading.Thread(target=run_http_server, daemon=True)
    http_thread.start()

    print("🤖 Bot WhatsApp Reporter démarré")
    print(f"   Canal requis: {CHANNEL_USERNAME}")
    print(f"   Admin ID: {ADMIN_ID}")
    print(f"   SMTP utilisés: {len(SMTP_ACCOUNTS)}")
    print(f"   Destinataires: {len(WHATSAPP_RECIPIENTS)}")
    print(f"   Port HTTP: {PORT} (ouvert pour Render)")

    last_id = 0
    while True:
        try:
            resp = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates", params={'timeout': 30, 'offset': last_id+1}, timeout=35).json()
            if resp.get('ok'):
                for upd in resp['result']:
                    last_id = upd['update_id']
                    if 'callback_query' in upd:
                        handle_callback(upd['callback_query'])
                    elif 'message' in upd:
                        msg = upd['message']
                        text = msg.get('text', '')
                        if text.startswith('/'):
                            handle_command(msg['chat']['id'], msg['from']['id'], text.split()[0].lower())
                        else:
                            handle_text(msg['chat']['id'], msg['from']['id'], text)
        except Exception as e:
            print(f"Erreur polling: {e}")
        time.sleep(1)

if __name__ == '__main__':
    main()
