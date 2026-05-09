import requests
import time
import random
import json
import smtplib
import os
import threading
import sys
from email.message import EmailMessage
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from collections import defaultdict

# ================= CONFIGURATION =================
ADMIN_ID = 7684684739
CHANNEL_USERNAME = "@wabanreport"
CHANNEL_LINK = "https://t.me/+tmrGH8UwjUw4ODY0"
PORT = int(os.environ.get('PORT', 8080))

# Paramètres SMTP (support multi-fournisseur)
SMTP_HOST = os.getenv('SMTP_HOST', 'smtp.gmail.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', 587))
SMTP_USE_SSL = os.getenv('SMTP_USE_SSL', 'false').lower() == 'true'
SMTP_DEBUG = os.getenv('SMTP_DEBUG', 'false').lower() == 'true'

# Délai entre chaque email (en secondes)
EMAIL_DELAY = float(os.getenv('EMAIL_DELAY', '2.0'))
MAX_REPORTS_PER_HOUR = int(os.getenv('MAX_REPORTS_PER_HOUR', 10))

# ================= GESTION DES COMPTES SMTP =================
def load_smtp_accounts():
    """
    Charge les comptes SMTP depuis les variables d'environnement et un fichier local.
    La variable SMTP_ACCOUNTS est prioritaire et doit être un tableau JSON.
    """
    accounts = []
    env_accounts = os.getenv('SMTP_ACCOUNTS', '[]')
    try:
        parsed = json.loads(env_accounts)
        if isinstance(parsed, list):
            accounts.extend(parsed)
            print(f"✅ {len(parsed)} compte(s) SMTP chargés depuis SMTP_ACCOUNTS (env)")
    except json.JSONDecodeError:
        print("⚠️ SMTP_ACCOUNTS dans l'environnement n'est pas un JSON valide")

    # Chargement depuis un fichier local (non persistant sur Render, mais utile en dev)
    if os.path.exists('smtp_accounts.json'):
        with open('smtp_accounts.json', 'r') as f:
            file_accounts = json.load(f)
            accounts.extend(file_accounts)
            print(f"✅ {len(file_accounts)} compte(s) SMTP chargés depuis smtp_accounts.json")

    # Déduplication par email
    seen = set()
    unique = []
    for acc in accounts:
        email = acc.get('email')
        if email and email not in seen:
            seen.add(email)
            unique.append(acc)
    return unique

SMTP_ACCOUNTS = load_smtp_accounts()

# ================= GESTION DES DESTINATAIRES =================
def load_recipients():
    env_recipients = os.getenv('WHATSAPP_RECIPIENTS', '[]')
    try:
        parsed = json.loads(env_recipients)
        if isinstance(parsed, list):
            print(f"✅ Destinataires chargés depuis l'environnement: {len(parsed)}")
            return parsed
    except json.JSONDecodeError:
        print("⚠️ WHATSAPP_RECIPIENTS invalide")

    # Fallback sur fichier
    if os.path.exists('recipients.json'):
        with open('recipients.json', 'r') as f:
            return json.load(f)
    # Valeurs par défaut
    return ["support@support.whatsapp.com", "abuse@whatsapp.com"]

WHATSAPP_RECIPIENTS = load_recipients()

# ================= ÉTAT GLOBAL =================
user_sessions = {}          # {user_id: {'step': ..., 'data': {}, 'timestamp': ...}}
user_stats = defaultdict(lambda: {'count': 0, 'last_reset': time.time()})
invalid_smtp = set()        # emails de comptes qui ont échoué récemment (temporaire)

# ================= CONNEXION SMTP AMÉLIORÉE =================
def create_smtp_connection(use_ssl=False):
    """Crée une connexion SMTP selon la configuration (STARTTLS ou SSL direct)."""
    if use_ssl:
        server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=20)
    else:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20)
    if SMTP_DEBUG:
        server.set_debuglevel(1)
    return server

def test_smtp_connection():
    """Teste la connectivité avec le premier compte SMTP valide."""
    if not SMTP_ACCOUNTS:
        print("⚠️ Aucun compte SMTP configuré")
        return
    acc = SMTP_ACCOUNTS[0]
    try:
        print(f"🔍 Test de connexion SMTP vers {SMTP_HOST}:{SMTP_PORT}...")
        server = create_smtp_connection(SMTP_USE_SSL)
        if not SMTP_USE_SSL:
            server.starttls()
        server.login(acc['email'], acc['password'])
        server.quit()
        print(f"✅ Connexion SMTP réussie avec {acc['email']}")
    except Exception as e:
        print(f"❌ Échec connexion SMTP: {e}")
        # Essayer le port alternatif si le principal échoue
        alt_port = 465 if SMTP_PORT == 587 else 587
        print(f"🔄 Tentative avec le port {alt_port}...")
        try:
            server = smtplib.SMTP_SSL(SMTP_HOST, alt_port, timeout=20)
            server.login(acc['email'], acc['password'])
            server.quit()
            print(f"✅ Connexion réussie sur le port {alt_port}")
        except Exception as e2:
            print(f"❌ Échec aussi sur le port {alt_port}: {e2}")

# ================= ENVOI D'EMAIL =================
def send_email(account, to, subject, body, sender_name):
    """Envoie un email. Retourne (succès, message_erreur)."""
    if account['email'] in invalid_smtp:
        return False, "Compte marqué comme invalide temporairement"
    try:
        msg = EmailMessage()
        msg.set_content(body, charset='utf-8')
        msg['Subject'] = subject
        msg['From'] = f'"{sender_name}" <{account["email"]}>'
        msg['To'] = to

        server = create_smtp_connection(SMTP_USE_SSL)
        if not SMTP_USE_SSL:
            server.starttls()
        server.login(account['email'], account['password'])
        server.send_message(msg)
        server.quit()
        print(f"✅ Envoyé de {account['email']} à {to}")
        return True, None
    except smtplib.SMTPAuthenticationError as e:
        err = f"Authentification échouée pour {account['email']}: {e}"
        print(f"❌ {err}")
        invalid_smtp.add(account['email'])   # marquer temporairement
        return False, err
    except smtplib.SMTPConnectError as e:
        err = f"Connexion SMTP impossible: {e}"
        print(f"❌ {err}")
        return False, err
    except Exception as e:
        err = str(e)
        print(f"❌ Erreur SMTP: {err}")
        return False, err

def send_with_retry(account, to, subject, body, sender_name, max_retries=2):
    """Tente l'envoi avec un compte, et réessaie avec un autre en cas d'échec."""
    for attempt in range(max_retries):
        if attempt > 0:
            # Choisir un autre compte
            available = [a for a in SMTP_ACCOUNTS if a['email'] != account['email'] and a['email'] not in invalid_smtp]
            if not available:
                return False, "Aucun compte SMTP alternatif disponible"
            account = random.choice(available)
            print(f"🔄 Nouvelle tentative avec {account['email']}")
        ok, err = send_email(account, to, subject, body, sender_name)
        if ok:
            return True, None
        time.sleep(1)
    return False, f"Échec après {max_retries} tentatives: {err}"

# ================= GÉNÉRATION DE RAPPORT =================
FIRST_NAMES = ["James", "Mary", "John", "Patricia", ...]  # ta liste complète
LAST_NAMES = ["Smith", "Johnson", "Williams", ...]       # ta liste complète

def random_sender_name():
    return f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"

def generate_detailed_report(number, category, report_index=1):
    # (identique à ta version, je le garde pour la cohérence)
    incidents = [
        {"title": "Spam and Phishing", "desc": f"Unsolicited messages from {number} promoting fake investments with phishing links.", "evidence": "Screenshots attached.", "action": "Permanently ban this number."},
        {"title": "Harassment and Threats", "desc": f"Since {datetime.now().strftime('%B %d')}, {number} has been sending abusive messages including death threats.", "evidence": "Chat logs available.", "action": "Suspend account and preserve logs."},
        {"title": "Impersonation and Fraud", "desc": f"The account {number} is impersonating my colleague using stolen photos, asking for money.", "evidence": "Screenshots of fake profile.", "action": "Block the account immediately."},
        {"title": "Illegal Content", "desc": f"{number} is sharing explicit adult content in a group that includes minors.", "evidence": "Screenshots of messages.", "action": "Remove the account."},
        {"title": "Privacy Violation", "desc": f"The user posted my private phone number on a public WhatsApp group without consent.", "evidence": "Screenshots available.", "action": "Remove the content."}
    ]
    incident = random.choice(incidents)
    return f"""URGENT: WhatsApp Terms of Service Violation - {incident['title']}

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

def generate_subject(number, category):
    return random.choice([
        f"Violation - {number} ({category})",
        f"Complaint: {category} from {number}",
        f"URGENT: {category} - {number}"
    ])

# ================= FONCTIONS TELEGRAM =================
def send_message(chat_id, text, reply_markup=None, parse_mode=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {'chat_id': chat_id, 'text': text}
    if reply_markup:
        payload['reply_markup'] = json.dumps(reply_markup)
    if parse_mode:
        payload['parse_mode'] = parse_mode
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Erreur send_message: {e}")

def edit_message(chat_id, msg_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/editMessageText"
    try:
        requests.post(url, json={'chat_id': chat_id, 'message_id': msg_id, 'text': text}, timeout=10)
    except Exception as e:
        print(f"Erreur edit_message: {e}")

def answer_callback(callback_id):
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery",
                  json={'callback_query_id': callback_id})

def send_message_and_get_id(chat_id, text):
    resp = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                         json={'chat_id': chat_id, 'text': text}, timeout=10).json()
    return resp.get('result') if resp.get('ok') else None

def is_valid_number(num):
    return num.startswith('+') and num[1:].replace(' ', '').isdigit() and len(num) >= 8

def is_admin(user_id):
    return user_id == ADMIN_ID

# ================= VÉRIFICATION MEMBRE =================
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
        print(f"Erreur check_membership: {e}")
        return False

def is_member(user_id):
    return check_membership(user_id)

def send_join_required(chat_id):
    keyboard = {
        'inline_keyboard': [
            [{'text': '📢 Rejoindre le canal', 'url': CHANNEL_LINK}],
            [{'text': "✅ J'ai rejoint", 'callback_data': 'verify_join'}]
        ]
    }
    send_message(chat_id,
        f"🚨 *Accès restreint*\n\n"
        f"Pour utiliser ce bot, vous devez d'abord rejoindre notre canal.\n\n"
        f"👥 Canal: {CHANNEL_USERNAME}\n\n"
        f"Rejoignez et cliquez sur *'J'ai rejoint'* pour continuer.\n\n"
        f"👤 Dev: @bestiemondie426",
        parse_mode='Markdown',
        reply_markup=keyboard)

# ================= GESTION DES SESSIONS UTILISATEUR =================
SESSION_TIMEOUT = 300  # 5 minutes d'inactivité

def clean_sessions():
    now = time.time()
    expired = [uid for uid, s in user_sessions.items() if now - s.get('timestamp', 0) > SESSION_TIMEOUT]
    for uid in expired:
        del user_sessions[uid]
        print(f"Session expirée pour {uid}")

def check_rate_limit(user_id):
    now = time.time()
    stats = user_stats[user_id]
    if now - stats['last_reset'] > 3600:
        stats['count'] = 0
        stats['last_reset'] = now
    return stats['count'] < MAX_REPORTS_PER_HOUR

def update_rate_limit(user_id, delta):
    stats = user_stats[user_id]
    stats['count'] += delta

# ================= COMMANDES =================
def handle_command(chat_id, user_id, cmd):
    if cmd not in ['/start', '/admin', '/help']:
        if not is_member(user_id):
            send_join_required(chat_id)
            return

    if cmd == '/start':
        user_sessions.pop(user_id, None)
        if is_member(user_id):
            msg = (
                "🚀 *WhatsApp Reporter Bot*\n\n"
                "/report - Signalement manuel\n"
                "/autoreport - Signalement automatique\n"
                "/stats - Votre quota horaire\n"
                "/help - Aide et informations"
            )
            send_message(chat_id, msg, parse_mode='Markdown')
        else:
            send_join_required(chat_id)

    elif cmd == '/help':
        send_message(chat_id, "🤖 Ce bot vous aide à signaler des numéros WhatsApp abusifs.\n\n"
                              "Commandes:\n"
                              "/report - Lancer un signalement avec choix de catégorie\n"
                              "/autoreport - Signalement automatique (catégorie aléatoire)\n"
                              "/stats - Voir votre quota de rapports restant ce heure\n\n"
                              "Pour toute question, contactez @bestiemondie426")

    elif cmd == '/stats':
        if not is_member(user_id):
            send_join_required(chat_id)
            return
        stats = user_stats[user_id]
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
            send_message(chat_id, "⏰ Limite horaire atteinte. Réessayez plus tard.")
            return
        user_sessions[user_id] = {'step': 'report_number', 'data': {}, 'timestamp': time.time()}
        send_message(chat_id, "📱 Envoyez le numéro WhatsApp avec indicatif: +243812345678")

    elif cmd == '/autoreport':
        if not is_member(user_id):
            send_join_required(chat_id)
            return
        if not check_rate_limit(user_id):
            send_message(chat_id, "⏰ Limite horaire atteinte.")
            return
        user_sessions[user_id] = {'step': 'autoreport_number', 'data': {}, 'timestamp': time.time()}
        send_message(chat_id, "📱 Envoyez le numéro WhatsApp avec indicatif:")

def admin_panel(chat_id):
    keyboard = {'inline_keyboard': [
        [{'text': '➕ Ajouter SMTP', 'callback_data': 'admin_add_smtp'}],
        [{'text': '➖ Supprimer SMTP', 'callback_data': 'admin_del_smtp'}],
        [{'text': '📋 Lister SMTP', 'callback_data': 'admin_list_smtp'}],
        [{'text': '📨 Ajouter destinataire', 'callback_data': 'admin_add_recipient'}],
        [{'text': '🗑 Supprimer destinataire', 'callback_data': 'admin_del_recipient'}],
        [{'text': '📋 Lister destinataires', 'callback_data': 'admin_list_recipients'}],
        [{'text': '📊 Stats', 'callback_data': 'admin_stats'}]
    ]}
    send_message(chat_id, "🔧 Panneau d'administration", reply_markup=keyboard)

# ================= HANDLERS ADMIN =================
def add_smtp_account(chat_id, email, password):
    global SMTP_ACCOUNTS
    if any(acc['email'] == email for acc in SMTP_ACCOUNTS):
        send_message(chat_id, f"❌ {email} existe déjà.")
        return
    SMTP_ACCOUNTS.append({"email": email, "password": password})
    # Sauvegarde locale (ne survivra pas sur Render, mais utile en dev)
    with open('smtp_accounts.json', 'w') as f:
        json.dump(SMTP_ACCOUNTS, f, indent=2)
    send_message(chat_id, f"✅ Compte SMTP ajouté: {email}")
    # Test immédiat
    try:
        server = create_smtp_connection(SMTP_USE_SSL)
        if not SMTP_USE_SSL:
            server.starttls()
        server.login(email, password)
        server.quit()
        send_message(chat_id, f"✅ Connexion test réussie avec {email}")
    except Exception as e:
        send_message(chat_id, f"⚠️ Ajouté mais test échoué: {e}")

def remove_smtp_account(chat_id, email):
    global SMTP_ACCOUNTS
    SMTP_ACCOUNTS = [acc for acc in SMTP_ACCOUNTS if acc['email'] != email]
    # Mettre à jour le fichier
    with open('smtp_accounts.json', 'w') as f:
        json.dump(SMTP_ACCOUNTS, f, indent=2)
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
        with open('recipients.json', 'w') as f:
            json.dump(WHATSAPP_RECIPIENTS, f, indent=2)
        send_message(chat_id, f"✅ Destinataire ajouté: {email}")
    else:
        send_message(chat_id, "❌ Existe déjà.")

def remove_recipient(chat_id, email):
    global WHATSAPP_RECIPIENTS
    if email in WHATSAPP_RECIPIENTS:
        WHATSAPP_RECIPIENTS.remove(email)
        with open('recipients.json', 'w') as f:
            json.dump(WHATSAPP_RECIPIENTS, f, indent=2)
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

def admin_stats(chat_id):
    msg = (f"📊 Statistiques:\n\n"
           f"Comptes SMTP: {len(SMTP_ACCOUNTS)}\n"
           f"Destinataires: {len(WHATSAPP_RECIPIENTS)}\n"
           f"Limite rapports/heure: {MAX_REPORTS_PER_HOUR}\n"
           f"Serveur SMTP: {SMTP_HOST}:{SMTP_PORT} (SSL: {SMTP_USE_SSL})\n"
           f"Intervalle email: {EMAIL_DELAY}s\n"
           f"Délai session: {SESSION_TIMEOUT}s")
    send_message(chat_id, msg)

# ================= TRAITEMENT DES MESSAGES =================
def handle_text(chat_id, user_id, text):
    session = user_sessions.get(user_id)
    if not session:
        if text.startswith('/'):
            handle_command(chat_id, user_id, text.split()[0].lower())
        else:
            send_message(chat_id, "Utilisez /start pour commencer")
        return

    # Mise à jour timestamp
    session['timestamp'] = time.time()
    step, data = session['step'], session['data']

    if step == 'report_number' and is_valid_number(text):
        data['number'] = text
        session['step'] = 'report_category'
        cats = ["Spam", "Harassment", "Fake Account", "Impersonation", "Illegal Activities",
                "Privacy Violation", "Threats", "Scam", "Abusive Content", "Other"]
        keyboard = {'inline_keyboard': [[{'text': c, 'callback_data': f'cat_{i}'}] for i, c in enumerate(cats)]}
        send_message(chat_id, "📂 Choisissez la catégorie:", reply_markup=keyboard)

    elif step == 'autoreport_number' and is_valid_number(text):
        data['number'] = text
        cats = ["Spam", "Harassment", "Fake Account", "Impersonation", "Illegal Activities",
                "Privacy Violation", "Threats", "Scam", "Abusive Content", "Other"]
        data['category'] = random.choice(cats)
        data['quantity'] = 1
        session['step'] = 'autoreport_confirm'
        send_message(chat_id, f"Numéro: {text}\nCatégorie: {data['category']}\nConfirmer ? (yes/no)")

    elif step == 'autoreport_confirm' and text.lower() in ('yes', 'y'):
        recipient = random.choice(WHATSAPP_RECIPIENTS)
        msg = send_message_and_get_id(chat_id, "📧 Envoi en cours...")
        if msg:
            send_single_report(chat_id, msg['message_id'], data['number'], data['category'], recipient)
            update_rate_limit(user_id, 1)
        del user_sessions[user_id]

    elif step == 'report_quantity':
        try:
            qty = int(text)
            if 1 <= qty <= 3:
                recipient = random.choice(WHATSAPP_RECIPIENTS)
                msg = send_message_and_get_id(chat_id, f"📧 Envoi de {qty} rapport(s)...")
                if msg:
                    send_multiple_reports(chat_id, msg['message_id'], data['number'], data['category'], qty, recipient)
                    update_rate_limit(user_id, qty)
                del user_sessions[user_id]
            else:
                send_message(chat_id, "❌ Entrez un nombre entre 1 et 3.")
        except ValueError:
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

# ================= ENVOI DES RAPPORTS =================
def send_single_report(chat_id, msg_id, number, category, recipient):
    if not SMTP_ACCOUNTS:
        edit_message(chat_id, msg_id, "❌ Aucun compte SMTP configuré.")
        return
    # Sélectionner un compte valide (évite ceux marqués invalides)
    available = [a for a in SMTP_ACCOUNTS if a['email'] not in invalid_smtp]
    if not available:
        edit_message(chat_id, msg_id, "❌ Tous les comptes SMTP sont temporairement inutilisables.")
        return
    account = random.choice(available)
    sender = random_sender_name()
    ok, err = send_with_retry(account, recipient, generate_subject(number, category),
                              generate_detailed_report(number, category), sender)
    if ok:
        edit_message(chat_id, msg_id, "✅ Envoi réussi !")
    else:
        edit_message(chat_id, msg_id, f"❌ Échec de l'envoi: {err}")

def send_multiple_reports(chat_id, msg_id, number, category, quantity, recipient):
    if not SMTP_ACCOUNTS:
        edit_message(chat_id, msg_id, "❌ Aucun compte SMTP configuré.")
        return
    success, fail = 0, 0
    available = [a for a in SMTP_ACCOUNTS if a['email'] not in invalid_smtp]
    if not available:
        edit_message(chat_id, msg_id, "❌ Tous les comptes SMTP sont temporairement inutilisables.")
        return
    for i in range(quantity):
        # Recalculer la liste à chaque itération au cas où un compte devient invalide
        available = [a for a in SMTP_ACCOUNTS if a['email'] not in invalid_smtp]
        if not available:
            edit_message(chat_id, msg_id, "❌ Plus de comptes SMTP disponibles.")
            break
        account = random.choice(available)
        sender = random_sender_name()
        ok, err = send_with_retry(account, recipient, generate_subject(number, category),
                                  generate_detailed_report(number, category, i+1), sender)
        if ok:
            success += 1
        else:
            fail += 1
            # Notifier l'admin en cas d'échec
            send_message(ADMIN_ID, f"⚠️ Échec rapport {i+1}/{quantity}: {err}")
        edit_message(chat_id, msg_id, f"📤 Progression: {i+1}/{quantity} | ✅ {success} | ❌ {fail}")
        time.sleep(EMAIL_DELAY)
    final = f"✅ Envoi terminé !\n\n📊 Rapports: {quantity}\n✅ Succès: {success}\n❌ Échecs: {fail}"
    edit_message(chat_id, msg_id, final)

# ================= CALLBACKS =================
def handle_callback(callback):
    user_id = callback['from']['id']
    chat_id = callback['message']['chat']['id']
    msg_id = callback['message']['message_id']
    data = callback['data']
    answer_callback(callback['id'])

    if data == 'verify_join':
        if is_member(user_id):
            edit_message(chat_id, msg_id, "✅ Vérification réussie ! Vous pouvez maintenant utiliser le bot.")
        else:
            edit_message(chat_id, msg_id, f"❌ Vous n'avez pas encore rejoint {CHANNEL_USERNAME}. Rejoignez puis réessayez.")
        return

    if not data.startswith(('admin_', 'del_', 'delrec_', 'cat_')):
        return

    # Catégories de rapport
    if data.startswith('cat_'):
        session = user_sessions.get(user_id)
        if session:
            idx = int(data.split('_')[1])
            cats = ["Spam", "Harassment", "Fake Account", "Impersonation", "Illegal Activities",
                    "Privacy Violation", "Threats", "Scam", "Abusive Content", "Other"]
            session['data']['category'] = cats[idx]
            session['step'] = 'report_quantity'
            edit_message(chat_id, msg_id, f"Catégorie: {cats[idx]}\n\nQuantité (1-3):")
        return

    # Administration
    if not is_admin(user_id):
        answer_callback(callback['id'], text="Accès refusé", show_alert=True)
        return

    if data == 'admin_add_smtp':
        user_sessions[user_id] = {'step': 'admin_add_smtp', 'data': {}, 'timestamp': time.time()}
        edit_message(chat_id, msg_id, "📧 Envoyez l'adresse email:")
    elif data == 'admin_del_smtp':
        if not SMTP_ACCOUNTS:
            edit_message(chat_id, msg_id, "Aucun compte.")
            return
        # Lister les comptes non protégés (ceux qui ne viennent pas de l'environnement)
        env_accounts = json.loads(os.getenv('SMTP_ACCOUNTS', '[]'))
        env_emails = {acc['email'] for acc in env_accounts}
        editable = [acc for acc in SMTP_ACCOUNTS if acc['email'] not in env_emails]
        if not editable:
            edit_message(chat_id, msg_id, "Aucun compte administrateur modifiable (les comptes d'environnement sont protégés).")
            return
        keyboard = {'inline_keyboard': [[{'text': acc['email'], 'callback_data': f'del_{acc["email"]}'}] for acc in editable]}
        edit_message(chat_id, msg_id, "Choisir le compte à supprimer:", reply_markup=keyboard)
    elif data.startswith('del_'):
        email = data[4:]
        remove_smtp_account(chat_id, email)
        edit_message(chat_id, msg_id, f"✅ Supprimé: {email}")
    elif data == 'admin_list_smtp':
        list_smtp_accounts(chat_id)
    elif data == 'admin_add_recipient':
        user_sessions[user_id] = {'step': 'admin_add_recipient', 'data': {}, 'timestamp': time.time()}
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
        admin_stats(chat_id)

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

# ================= POLLING PRINCIPAL =================
def main():
    # Nettoyage périodique des sessions
    def periodic_clean():
        while True:
            time.sleep(60)
            clean_sessions()
            # Réinitialisation périodique des comptes invalides (toutes les 10 minutes)
            if int(time.time()) % 600 < 60:
                invalid_smtp.clear()

    threading.Thread(target=periodic_clean, daemon=True).start()
    http_thread = threading.Thread(target=run_http_server, daemon=True)
    http_thread.start()

    print("🤖 WhatsApp Reporter Bot v2.0 (robuste)")
    print(f"   Canal requis: {CHANNEL_USERNAME}")
    print(f"   Admin ID: {ADMIN_ID}")
    print(f"   SMTP: {SMTP_HOST}:{SMTP_PORT}, SSL: {SMTP_USE_SSL}")
    print(f"   Comptes SMTP chargés: {len(SMTP_ACCOUNTS)}")
    print(f"   Destinataires: {len(WHATSAPP_RECIPIENTS)}")
    print(f"   Intervalle email: {EMAIL_DELAY}s, limite/heure: {MAX_REPORTS_PER_HOUR}")

    test_smtp_connection()

    last_id = 0
    while True:
        try:
            resp = requests.get(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
                params={'timeout': 30, 'offset': last_id + 1},
                timeout=35
            ).json()
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
        except requests.exceptions.ReadTimeout:
            continue
        except Exception as e:
            print(f"Erreur polling: {e}")
            time.sleep(2)

if __name__ == '__main__':
    # Chargement du token
    TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
    if not TELEGRAM_TOKEN:
        print("ERREUR: TELEGRAM_TOKEN non défini")
        sys.exit(1)
    main()
