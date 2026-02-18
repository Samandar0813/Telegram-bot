import os, json
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup
from aiogram.utils import executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

from docx import Document
from pptx import Presentation

# Gemini AI SDK
from google import genai
from google.genai import types

# --- CONFIGURATION ---
API_TOKEN = "8334678189:AAFOX5_iRnpd57hFPE9cw0amGeyRfJYQNkg"
ADMIN_ID = 6485288387   # Bu yerga o‘zingizning admin ID yozing
BOT_MODEL = "gemini-2.5-flash"

# Bot va FSM
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# Users limit
LIMIT = 5
users_file = "users.json"

# ================= USERS =================
if os.path.exists(users_file):
    with open(users_file, "r") as f:
        users_data = json.load(f)
else:
    users_data = {}

def save_users():
    with open(users_file, "w") as f:
        json.dump(users_data, f)

def can_use(user_id):
    now = datetime.now().timestamp()
    user = users_data.get(str(user_id))
    if not user:
        users_data[str(user_id)] = {"count": 0, "timestamp": now}
        save_users()
        return True
    last = datetime.fromtimestamp(user["timestamp"])
    if datetime.now() - last > timedelta(days=30):
        user["count"] = 0
        user["timestamp"] = now
        save_users()
    return user["count"] < LIMIT

def add_use(user_id):
    users_data[str(user_id)]["count"] += 1
    save_users()

# ================= FSM STATES =================
class BotStates(StatesGroup):
    choosing_degree = State()
    choosing_task = State()
    waiting_for_topic = State()

# ================= KEYBOARDS =================
degree_keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
degree_keyboard.add("🏫 Maktab o'qituvchisi")
degree_keyboard.add("🎓 Texnikum o'qituvchisi")
degree_keyboard.add("👩‍🏫 Universitet o'qituvchisi")

task_keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
task_keyboard.add("📚 Dars ishlanma", "📝 Tezis")
task_keyboard.add("📄 Maqola", "🧪 Test", "📊 Taqdimot")

restart_keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
restart_keyboard.add("🔄 Yana boshlash")

# ================= START HANDLER =================
@dp.message_handler(commands=['start'], state='*')
async def start_bot(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer("👋 Salom! Darajani tanlang:", reply_markup=degree_keyboard)
    await BotStates.choosing_degree.set()

# ================= DEGREE SELECT =================
@dp.message_handler(lambda m: m.text in [
    "🏫 Maktab o'qituvchisi",
    "🎓 Texnikum o'qituvchisi",
    "👩‍🏫 Universitet o'qituvchisi"
], state=BotStates.choosing_degree)
async def degree_selected(message: types.Message, state: FSMContext):
    await state.update_data(degree=message.text)
    await message.answer("📌 Vazifani tanlang:", reply_markup=task_keyboard)
    await BotStates.choosing_task.set()

# ================= TASK SELECT =================
@dp.message_handler(lambda m: m.text in [
    "📚 Dars ishlanma","📝 Tezis","📄 Maqola","🧪 Test","📊 Taqdimot"
], state=BotStates.choosing_task)
async def task_selected(message: types.Message, state: FSMContext):
    await state.update_data(task=message.text)
    await message.answer("✏️ Endi mavzuni yozing:", reply_markup=types.ReplyKeyboardRemove())
    await BotStates.waiting_for_topic.set()

# ================= GEMINI AI REQUEST =================
def generate_with_gemini(degree, task, topic):
    prompt = f"Daraja: {degree}\nVazifa: {task}\nMavzu: {topic}\nMukammal matn yozing:"

    # API kalitini o‘qish
    api_key = os.getenv("GOOGLE_API_KEY")

    # Gemini klientini yaratish
    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model=BOT_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.8,
            max_output_tokens=1200
        )
    )

    return response.text

# ================= TOPIC HANDLER =================
@dp.message_handler(state=BotStates.waiting_for_topic)
async def topic_received(message: types.Message, state: FSMContext):
    user_id = message.from_user.id

    if not can_use(user_id):
        await message.answer("❌ Limit tugadi. Obuna oling 🙂", reply_markup=restart_keyboard)
        await state.finish()
        return

    data = await state.get_data()
    degree = data["degree"]
    task = data["task"]
    topic = message.text

    add_use(user_id)

    # AI yozgan matn
    full_text = generate_with_gemini(degree, task, topic)

    # Fayl yaratish
    if task == "📊 Taqdimot":
        filename = f"{user_id}.pptx"
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        slide.shapes.title.text = topic
        slide.placeholders[1].text = full_text
        prs.save(filename)
    else:
        filename = f"{user_id}.docx"
        doc = Document()
        doc.add_heading(task, 0)
        doc.add_paragraph(full_text)
        doc.save(filename)

    await message.answer_document(open(filename, "rb"), caption="✅ Tayyor")
    os.remove(filename)

    await message.answer("🔄 Yana boshlash uchun:", reply_markup=restart_keyboard)
    await state.finish()

# ================= RESTART =================
@dp.message_handler(lambda m: m.text == "🔄 Yana boshlash")
async def restart(message: types.Message, state: FSMContext):
    await start_bot(message, state)

# ================= ADMIN PANEL =================
@dp.message_handler(lambda m: m.from_user.id == ADMIN_ID)
async def admin_panel(message: types.Message):
    text = "👑 Admin Panel\n\nFoydalanuvchilar statistikasi:\n"
    for uid, info in users_data.items():
        text += f"{uid} → {info['count']}\n"
    text += f"\nJoriy limit: {LIMIT}"
    await message.answer(text)

# ================= RUN BOT =================
if __name__ == "__main__":
    print("Bot ishladi")
    executor.start_polling(dp, skip_updates=True)

