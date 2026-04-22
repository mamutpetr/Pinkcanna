import requests
import os

# Отримуємо токен виключно із системних змінних
POSTER_TOKEN = os.getenv("POSTER_TOKEN")

def get_poster_products():
    if not POSTER_TOKEN:
        print("❌ Помилка: POSTER_TOKEN не знайдено у системних змінних (ENV).")
        return

    url = f"https://joinposter.com/api/menu.getProducts?token={POSTER_TOKEN}"
    print("⏳ Отримую список товарів з Poster...\n")
    
    try:
        response = requests.get(url, timeout=15)
        data = response.json()
        
        if "response" in data:
            products = data["response"]
            
            print("-" * 60)
            print(f"{'POSTER_ID':<10} | {'ЦІНА (грн)':<12} | {'НАЗВА ТОВАРУ'}")
            print("-" * 60)
            
            for item in products:
                product_id = item.get("product_id")
                name = item.get("product_name")
                
                # Poster віддає ціну в копійках, ділимо на 100
                price_dict = item.get("price", {})
                price_kopecks = int(price_dict.get("1", 0)) if isinstance(price_dict, dict) else 0
                price_uah = price_kopecks / 100
                
                print(f"{product_id:<10} | {price_uah:<12} | {name}")
                
            print("-" * 60)
            print(f"✅ Всього знайдено товарів: {len(products)}")
            
        else:
            print(f"❌ Помилка API Poster. Відповідь сервера: {data}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Помилка з'єднання з Poster: {e}")

if __name__ == "__main__":
    get_poster_products()

