import httpx
import logging
from config.config import settings
import asyncio

logger = logging.getLogger(__name__)

class PlategaPay:
    BASE_URL = settings.BASE_URL_PLATEGA

    def __init__(self, merchant_id, api_key):
        self.headers = {
            "X-MerchantId" : merchant_id,
            "X-Secret" : api_key,
            "Content-Type" : "application/json"
        }

    async def create_invoice(
        self,
        user_id: int,
        amount: float,
        payment_method: int = 2,
        description: str = "Покупка цифрового товара"
        ) -> dict | None:

        url = f"{self.BASE_URL}/transaction/process"

        bot_link = "https://t.me/alembic_store_bot"
        user_email = f"{user_id}@telegram.org"
        
        payload = {
            "paymentMethod" : payment_method,
            "paymentDetails" : {
                "amount" : amount,
                "currency" : "RUB"
            },
            "description" : description,
            "return" : bot_link,
            "failedUrl" : bot_link,
            "metadata" : {
                "user_email" : user_email
            }
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.post(url=url, headers=self.headers, json=payload)

                response.raise_for_status()
                data = response.json()

                return {
                    "transactionId" : data.get("transactionId"),
                    "payment_url" : data.get("redirect"),
                    "status" : data.get("status")
                }
                
            except httpx.HTTPStatusError as e:
                logger.error(
                    f"[Platega API Error] Статус: {e.response.status_code} | "
                    f"Ответ сервера: {e.response.text}"
                )
                return None
            
            except httpx.RequestError as e:
                logger.error(f"[Platega Network Error] Сбой соединения с {e.request.url}: {e}")
                return None
            
            except Exception as e:
                logger.exception(f"[Platega Unexpected Error] Непредвиденная ошибка: {e}")
                return None

    async def get_invoice(self, transaction_id: str) -> dict | None:
        url = f"{self.BASE_URL}/transaction/{transaction_id}"

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.get(url=url, headers=self.headers)
                response.raise_for_status()

                data = response.json()

                return {
                    "id" : data.get("id") or data.get("transactionId"),
                    "status" : data.get("status"),
                    "amount" : data.get("paymentDetails", {}).get("amount", 0)
                }
            except httpx.HTTPStatusError as e:
                logger.error(
                    f"[Platega API Error] Ошибка проверки {transaction_id}: "
                    f"Статус {e.response.status_code} | Ответ: {e.response.text}"
                )
                return None
            
            except httpx.RequestError as e:
                logger.error(f"[Platega Network Error] Сбой соединения при проверке {transaction_id}: {e}")
                return None
            
            except Exception as e:
                logger.exception(f"[Platega Unexpected Error] Сбой проверки {transaction_id}: {e}")
                return None
            
