import asyncio
import json
from config.config import settings
from openai import AsyncOpenAI
from pydantic import BaseModel

client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=settings.OPENROUTER_API_KEY,
)


class ResponseScheme(BaseModel):
  is_approved: bool
  reason: str


async def check_review_with_ai(review_text: str) -> ResponseScheme:
  text = (review_text or "").strip()
  if not text:
    return ResponseScheme(is_approved=False, reason="Пустой текст")

  prompt = (
        "Ты — модератор отзывов в магазине цифровых товаров.\n"
        f"Отзыв покупателя: «{text}»\n\n"
        "ПРАВИЛА:\n"
        "1. is_approved = true:\n"
        "   - Положительные или нейтральные отзывы, разговорный сленг одобрения "
        "(«нормально», «не ну нормально», «пойдет», «сойдет», «топ», «кайф», «все пришло», «норм»).\n"
        "2. is_approved = false:\n"
        "   - Прямой негатив и призывы не брать («не берите», «не советую», «говно», «фигня», «не очень», «ужасно»).\n"
        "   - Претензии и проблемы (невалид, обман, не работает, скам, верните деньги).\n"
        "   - Оскорбления, мат, спам.\n\n"
        "Формат ответа СТРОГО JSON без markdown:\n"
        '{"is_approved": true, "reason": "кратко до 4 слов"}'
    )
  
  try:
    response = await client.chat.completions.create(
        model="openrouter/free",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
    )

    raw_text = (response.choices[0].message.content or "").strip()

    # убираем ``` если модель их добавила
    raw_text = raw_text.replace("```json", "").replace("```", "").strip()

    start = raw_text.find("{")
    end = raw_text.rfind("}")

    if start == -1 or end == -1:
      return ResponseScheme(
          is_approved=False, reason="Модель вернула пустой или некорректный ответ"
      )
     
    data = json.loads(raw_text[start : end + 1])
    return ResponseScheme(
        is_approved=data.get("is_approved", False),
        reason=data.get("reason", "Без описания"),
    )

  except Exception as e:
    return ResponseScheme(is_approved=False, reason=f"Ошибка: {e}")


# async def main():
#   test = await check_review_with_ai("кайф")
#   print(test)

# if __name__ == "__main__":
#   asyncio.run(main())