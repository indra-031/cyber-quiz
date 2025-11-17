import logging
import random
import os
import json
from datetime import datetime
from telegram import Poll
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, ContextTypes

# ================== CONFIG ==================
BOT_TOKEN = "<TELEGRAM_BOT_TOKEN_HERE>"
CHAT_ID = -<TELEGRAM_CHAT_ID_HERE>          # Group chat ID
TOPIC_ID = None        # Topic/thread ID
QUIZ_FILE = "questions.txt"       # Questions source file
SENT_FILE = "sent_questions.txt"  # Stores previously sent questions
SCORES_FILE = "scores.json"       # Monthly scores
RESET_FILE = "last_reset.txt"     # Month tracking file
# ============================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ====== SENT QUESTION HANDLING ======
def load_sent_questions():
    if not os.path.exists(SENT_FILE):
        return set()
    with open(SENT_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())


def save_sent_question(question_text):
    with open(SENT_FILE, "a", encoding="utf-8") as f:
        f.write(question_text + "\n")


# ====== LOAD QUESTIONS ======
def load_questions():
    questions = []
    try:
        with open(QUIZ_FILE, "r", encoding="utf-8") as f:
            blocks = f.read().strip().split("\n\n")

        for block in blocks:
            lines = block.strip().split("\n")
            if len(lines) < 3:
                continue

            question_text = lines[0].replace("[ Poll : ", "").replace("]", "").strip()
            options = []
            correct_index = None
            explanation = ""

            for idx, line in enumerate(lines[1:]):
                if line.startswith("*"):
                    options.append(line[2:].strip())
                    correct_index = idx
                elif line.startswith("-"):
                    options.append(line[2:].strip())
                elif line.startswith("> Explanation:"):
                    explanation = "\n".join(lines[idx+2:]).strip()
                    break

            if question_text and options and correct_index is not None:
                questions.append({
                    "question": question_text,
                    "options": options,
                    "correct_index": correct_index,
                    "explanation": explanation
                })

    except Exception as e:
        logger.error(f"Error loading questions: {e}")

    return questions


# ====== SCORE SYSTEM ======
def load_scores():
    if not os.path.exists(SCORES_FILE):
        return {}
    with open(SCORES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_scores(scores):
    with open(SCORES_FILE, "w", encoding="utf-8") as f:
        json.dump(scores, f, indent=4)


def check_month_reset():
    """Reset leaderboard if month has changed."""
    now = datetime.now()
    current_month = f"{now.year}-{now.month}"

    if not os.path.exists(RESET_FILE):
        with open(RESET_FILE, "w") as f:
            f.write(current_month)
        return False

    with open(RESET_FILE, "r") as f:
        last_month = f.read().strip()

    if last_month != current_month:
        # RESET MONTH
        with open(SCORES_FILE, "w") as f:
            f.write("{}")
        with open(RESET_FILE, "w") as f:
            f.write(current_month)
        return True

    return False


# ====== QUIZ ANSWER HANDLER ======
async def handle_quiz_answer(update, context: ContextTypes.DEFAULT_TYPE):
    query = update.poll_answer
    if not query:
        return

    user_id = query.user.id
    selected = query.option_ids[0]

    correct_option = context.bot_data.get("last_correct_option")
    if correct_option is None:
        return

    scores = load_scores()

    if str(user_id) not in scores:
        scores[str(user_id)] = {"name": query.user.first_name, "score": 0}

    if selected == correct_option:
        scores[str(user_id)]["score"] += 1

    save_scores(scores)


# ====== SEND QUIZ ======
async def send_quiz():
    check_month_reset()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    questions = load_questions()
    if not questions:
        logger.error("No questions found.")
        return

    sent = load_sent_questions()
    available = [q for q in questions if q["question"] not in sent]

    if not available:
        open(SENT_FILE, "w").close()  # reset sent questions
        available = questions

    question = random.choice(available)

    # Save correct answer to bot data
    app.bot_data["last_correct_option"] = question["correct_index"]

    # Send quiz
    await app.bot.send_poll(
        chat_id=CHAT_ID,
        message_thread_id=TOPIC_ID,
        question=question['question'],
        options=question['options'],
        type=Poll.QUIZ,
        correct_option_id=question['correct_index'],
        explanation=question['explanation'],
        explanation_parse_mode="HTML",
        is_anonymous=False
    )

    save_sent_question(question["question"])
    logger.info(f"Sent quiz: {question['question']}")

    # Poll answer handler
    app.add_handler(CallbackQueryHandler(handle_quiz_answer))

    await app.shutdown()


# MAIN EXECUTION
if __name__ == "__main__":
    import asyncio
    asyncio.run(send_quiz())

