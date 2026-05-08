import smtplib
import time
import random
from email.message import EmailMessage

class SMTPPool:
    def __init__(self, accounts):
        self.accounts = accounts  # liste de dict {email, password}
        self.failures = {acc['email']: 0 for acc in accounts}
        self.conn = None

    def _get_working_account(self):
        # retourne un compte qui a échoué le moins
        if not self.accounts:
            return None
        # exclure ceux avec trop d'échecs (>3)
        ok = [acc for acc in self.accounts if self.failures.get(acc['email'],0) < 3]
        if not ok:
            ok = self.accounts
        return random.choice(ok)

    def send_email(self, to, subject, body):
        acc = self._get_working_account()
        if not acc:
            return False, "No SMTP account available"
        try:
            msg = EmailMessage()
            msg.set_content(body)
            msg["Subject"] = subject
            msg["From"] = acc['email']
            msg["To"] = to

            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
                server.login(acc['email'], acc['password'])
                server.send_message(msg)
            return True, "OK"
        except Exception as e:
            self.failures[acc['email']] += 1
            return False, str(e)

    def send_multiple(self, to, subject, body, count):
        successes = 0
        fails = 0
        details = []
        for i in range(count):
            subj = f"{subject} #{i+1}"
            ok, msg = self.send_email(to, subj, body + f"\n\n--- Rapport {i+1} ---")
            if ok:
                successes += 1
            else:
                fails += 1
            details.append({"index": i+1, "success": ok, "error": msg if not ok else None})
            time.sleep(2)  # délai entre les emails
        return successes, fails, details
