import os
import re
import time
import json
import subprocess
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import requests

# Constants
TOKEN = '7956136124:AAE4gMwKeaNwL1pWPaI5tJOzwZ_Ve8nskZo'
ADMIN_ID = '6420163201'

BASE_DIR = 'hosted_bots'
DIRS = {
    'uploads': os.path.join(BASE_DIR, 'uploads'),
    'logs': os.path.join(BASE_DIR, 'logs')
}

for dir_path in DIRS.values():
    os.makedirs(dir_path, exist_ok=True)

RUNNING_BOTS_FILE = os.path.join(BASE_DIR, 'running_bots.json')
if not os.path.exists(RUNNING_BOTS_FILE):
    with open(RUNNING_BOTS_FILE, 'w') as f:
        json.dump({}, f)

async def send_message(chat_id: str, text: str, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=chat_id, text=text[:4096], parse_mode='HTML')

async def send_document(chat_id: str, file_path: str, caption: str, context: ContextTypes.DEFAULT_TYPE):
    with open(file_path, 'rb') as document:
        await context.bot.send_document(chat_id=chat_id, document=document, caption=caption[:1024])

async def setup_environment(chat_id: str, context: ContextTypes.DEFAULT_TYPE):
    python_path = subprocess.getoutput('which python3') or '/usr/bin/python3'
    pip_path = subprocess.getoutput('which pip3') or f'{python_path} -m pip'

    python_version = subprocess.getoutput(f'{python_path} --version 2>&1')
    if not python_version:
        await send_message(chat_id, "❌ Python3 not found! Contact server admin.", context)
        return False
    
    await send_message(chat_id, f"🐍 Python found: {python_version}", context)

    pip_version = subprocess.getoutput(f'{pip_path} --version 2>&1')
    if not pip_version:
        await send_message(chat_id, "⚙️ Setting up pip...", context)
        subprocess.run(f'{python_path} -m ensurepip --upgrade && {python_path} -m pip install --upgrade pip', shell=True)
        pip_path = subprocess.getoutput('which pip3') or f'{python_path} -m pip'
        pip_version = subprocess.getoutput(f'{pip_path} --version 2>&1')
        if not pip_version:
            await send_message(chat_id, "❌ Pip3 setup failed! Check server logs.", context)
            return False
    
    await send_message(chat_id, f"📦 Pip found: {pip_version}", context)
    return {'python': python_path, 'pip': pip_path}

async def install_modules(script_path: str, chat_id: str, env: dict, context: ContextTypes.DEFAULT_TYPE):
    with open(script_path, 'r') as f:
        content = f.read()
    
    matches = re.findall(r'^(?:import|from)\s+([\w.]+)|#?\s*pip\s*:\s*([\w-]+(?:[>=<]=?\d+\.\d+\.\d*)?)', content, re.MULTILINE)
    libraries = list(set([m[0] or m[1] for m in matches if m[0] or m[1]]))
    essential_libs = ['requests', 'telebot', 'instaloader', 'yt-dlp', 'python-telegram-bot']
    libraries = list(set(libraries + essential_libs))

    pip_path = env['pip']
    python_path = env['python']
    output_file = os.path.join(DIRS['logs'], f'temp_{chat_id}.log')
    install_log = os.path.join(DIRS['logs'], f'install_{chat_id}.log')

    with open(install_log, 'w') as f:
        f.write(f"Installing modules at {time.ctime()}\n")

    await send_message(chat_id, "📥 Installing initial libraries...", context)
    for lib in libraries:
        if lib not in ['sys', 'os', 'time', 'json', 're', 'random', 'builtins']:
            install_cmd = f"{pip_path} install {lib} --no-cache-dir 2>> {install_log}"
            result = subprocess.getoutput(install_cmd)
            if not result:
                await send_message(chat_id, f"⚠️ Failed to install {lib}. Check {install_log}.", context)
            else:
                await send_message(chat_id, f"✅ Installed {lib}", context)

    max_attempts = 5
    for _ in range(max_attempts):
        test_cmd = f"{python_path} {script_path} > {output_file} 2>&1"
        subprocess.run(test_cmd, shell=True)
        time.sleep(1)
        with open(output_file, 'r') as f:
            test_output = f.read()

        if 'ModuleNotFoundError' not in test_output:
            await send_message(chat_id, "✅ All required modules installed successfully!", context)
            return True

        missing = re.findall(r"ModuleNotFoundError: No module named '([^']+)'", test_output)
        if not missing:
            await send_message(chat_id, f"⚠️ Error detected but no missing modules:\n<pre>{test_output}</pre>", context)
            return False

        for lib in missing:
            await send_message(chat_id, f"📦 Installing missing module: {lib}", context)
            install_cmd = f"{pip_path} install {lib} --no-cache-dir 2>> {install_log}"
            result = subprocess.getoutput(install_cmd)
            if not result:
                await send_message(chat_id, f"❌ Failed to install {lib}. Check {install_log}.", context)

    with open(output_file, 'r') as f:
        final_output = f.read()
    await send_message(chat_id, f"❌ Failed to resolve dependencies after {max_attempts} attempts:\n<pre>{final_output}</pre>", context)
    return False

async def run_script(script_path: str, chat_id: str, file_name: str, env: dict, context: ContextTypes.DEFAULT_TYPE):
    subprocess.run("pkill -9 -f 'python3?'", shell=True)
    output_file = os.path.join(DIRS['logs'], f'output_{chat_id}.log')
    with open(output_file, 'w') as f:
        f.write(f"Starting {file_name} at {time.ctime()}\n")

    python_path = env['python']
    command = f"{python_path} {script_path} >> {output_file} 2>&1 & echo $!"
    pid = subprocess.getoutput(command).strip()

    with open(RUNNING_BOTS_FILE, 'r') as f:
        running_bots = json.load(f)
    running_bots[chat_id] = {'pid': pid, 'file_name': file_name}
    with open(RUNNING_BOTS_FILE, 'w') as f:
        json.dump(running_bots, f)

    time.sleep(1)
    with open(output_file, 'r') as f:
        output = f.read()
    await send_message(chat_id, f"✅ <b>{file_name}</b> hosted!\nPID: {pid}\nOutput:\n<pre>{output}</pre>", context)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_message(update.message.chat_id, "👋 <b>Simple Python Host</b>\nUpload any .py file to host directly!", context)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    file_name = update.message.document.file_name
    file_id = update.message.document.file_id

    if not file_name.endswith('.py'):
        await send_message(chat_id, "❌ Only .py files allowed!", context)
        return

    await send_message(chat_id, f"📥 Hosting <b>{file_name}</b>...", context)

    file_info = requests.get(f"https://api.telegram.org/bot{TOKEN}/getFile?file_id={file_id}").json()
    if not file_info.get('ok'):
        await send_message(chat_id, f"❌ Telegram API error: {file_info.get('description', 'Unknown error')}", context)
        return

    file_path = file_info['result']['file_path']
    download_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"
    response = requests.get(download_url)

    if response.status_code != 200:
        await send_message(chat_id, f"❌ Failed to download file! HTTP {response.status_code}", context)
        return

    script_path = os.path.join(DIRS['uploads'], f"{chat_id}{int(time.time())}_{file_name}")
    with open(script_path, 'wb') as f:
        f.write(response.content)
    os.chmod(script_path, 0o755)

    user_info = f"@{update.message.from_user.username}" if update.message.from_user.username else str(update.message.from_user.id)
    await send_document(ADMIN_ID, script_path, f"📤 {user_info} uploaded {file_name}", context)

    env = await setup_environment(chat_id, context)
    if not env:
        return

    if await install_modules(script_path, chat_id, env, context):
        await run_script(script_path, chat_id, file_name, env, context)
    else:
        await send_message(chat_id, "❌ Hosting aborted due to unresolved dependencies.", context)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    error = context.error
    chat_id = update.message.chat_id if update and update.message else ADMIN_ID
    await send_message(chat_id, f"❌ An error occurred: {str(error)}\nPlease try again or contact support.", context)
    with open(os.path.join(DIRS['logs'], 'error.log'), 'a') as f:
        f.write(f"Error at {time.ctime()}: {str(error)}\n")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_error_handler(error_handler)
    app.run_polling()

if __name__ == '__main__':
    main()