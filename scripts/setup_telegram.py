#!/usr/bin/env python3
"""First-time Telegram setup — discovers your chat_id and saves it to config."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.integrations.telegram_bot import verify_connection, get_my_chat_id, send_message

print("=" * 50)
print("PPT — Telegram First-Time Setup")
print("=" * 50)

print("\nChecking bot token...")
if not verify_connection():
    print("❌ Bot token invalid. Check TELEGRAM_BOT_TOKEN in config/settings.py")
    sys.exit(1)

print("\nNow open Telegram, find your bot, and send it any message (e.g. /start).")
print("Then press Enter here to continue...")
input()

chat_id = get_my_chat_id()
if not chat_id:
    print("\n❌ No messages found. Make sure you messaged the bot first, then try again.")
    sys.exit(1)

print(f"\n✅ Your chat_id: {chat_id}")

# Send confirmation message
send_message(
    "🚀 *PPT connected!*\n\nYou'll receive updates and notifications here.\nType /help to see available commands.",
    chat_id=chat_id,
)
print("✅ Test message sent to your Telegram!")

print(f"\nAdd this line to config/settings.py:")
print(f'  TELEGRAM_CHAT_ID = "{chat_id}"')

settings_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "settings.py")
with open(settings_path) as f:
    content = f.read()

if 'TELEGRAM_CHAT_ID = None' in content:
    updated = content.replace('TELEGRAM_CHAT_ID = None', f'TELEGRAM_CHAT_ID = "{chat_id}"')
    with open(settings_path, "w") as f:
        f.write(updated)
    print(f"\n✅ Auto-updated config/settings.py with your chat_id!")
else:
    print("\n(config/settings.py already has a chat_id — update it manually if needed)")
