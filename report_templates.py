import random
import time

DESCRIPTION_TEMPLATES = [
    "This number is sending spam messages with malicious links to many contacts.",
    "Harassment and threats received repeatedly from this number.",
    "Impersonating a known person to scam others.",
    "Shared my private phone number without consent in a group.",
    "Promoting illegal activities including drug sales and phishing.",
    "Sent unsolicited explicit images and videos.",
    "Financial scam: asking for money under false pretenses.",
    "Fake account using my profile picture to contact my friends.",
    "Sending virus-infected attachments and fake lottery messages.",
    "Coordinated spam campaign in multiple groups."
]

def get_random_description():
    base = random.choice(DESCRIPTION_TEMPLATES)
    return base + f"\n\nReported on {time.strftime('%Y-%m-%d %H:%M:%S')}. Please investigate."

def get_random_category(categories):
    return random.choice(categories)

def get_random_quantity(min_q, max_q, max_user_limit):
    max_allowed = min(max_q, max_user_limit)
    if max_allowed < min_q:
        return min_q
    return random.randint(min_q, max_allowed)
