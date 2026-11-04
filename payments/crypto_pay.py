import httpx
from config.config import settings
import logging

logger = logging.getLogger(__name__)

class CryptoPay:
    BASE_URL = settings.BASE_URL_CRYPTO

    def __init__(self,token: str):
        self.headers = { "Crypto-Pay-API-Token" : token}

    async def create_invoice(self, amount: float | int | str, fiat: str = 'RUB', accepted_assets: list[str] | None = None,) -> dict | None:

        data = {
            "currency_type" : "fiat",
            "fiat" : fiat,
            "amount" : str(amount),
        }

        if accepted_assets:
            data["accepted_assets"] = ",".join(accepted_assets)

        async with httpx.AsyncClient(timeout=10.0) as session:
            try:
                response = await session.post(
                    f"{self.BASE_URL}createInvoice",
                    headers=self.headers,
                    json=data,
                )
                response.raise_for_status()
                result = response.json()

                if not result.get("ok"):
                    logger.error(f"[CryptoPay Error] Ошибка API: {result.get('error')}")
                    return None
                    
                return result.get("result")
            
            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                logging.error(f"[CryptoPay Error] Сбой сети или HTTP: {e}")
                return None
            except Exception as e:
                logger.exception(f"[CryptoPay Error] Непредвиденная ошибка: {e}")
                return None


    async def get_invoice(self, invoice_id: int | str) -> dict | None:
        
        params = {"invoice_ids": str(invoice_id)}


        async with httpx.AsyncClient(timeout=10.0) as session:
            try:
                response = await session.get(
                    f"{self.BASE_URL}getInvoices",
                    headers=self.headers,
                    params=params,
                )

                response.raise_for_status()
                result = response.json()

                if not result.get("ok"):
                    logger.error(f"[CryptoPay Error] Ошибка API: {result.get('error')}")
                    return None
                
                items = result.get("result",{}).get("items",[])

                return items[0] if items else None
            
            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                logger.error(f"[CryptoPay Error] Сбой сети или HTTP: {e}")
                return None
            
            except Exception as e:
                logger.exception(f"[CryptoPay Error] Непредвиденная ошибка: {e}")
                return None