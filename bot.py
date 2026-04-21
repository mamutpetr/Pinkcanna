import requests
import os

# Беремо токен із системних змінних
POSTER_TOKEN = os.getenv("POSTER_TOKEN")

def get_all_products():
    if not POSTER_TOKEN:
        print("❌ POSTER_TOKEN не знайдено у системних змінних (ENV).")
        return

    url = f"https://joinposter.com/api/menu.getProducts?token={POSTER_TOKEN}"
    
    print("⏳ Отримую список товарів з Poster...\n")
    try:
        response = requests.get(url).json()
        
        if "response" in response:
            products = response["response"]
            for item in products:
                product_id = item.get("product_id")
                name = item.get("product_name")
                price = int(item.get("price", { "1": 0 }).get("1", 0)) / 100
                
                print(f"✅ ID: {product_id} | Товар: {name} | Ціна: {price} грн")
        else:
            print(f"❌ Помилка API: {response}")
            
    except Exception as e:
        print(f"❌ Помилка з'єднання: {e}")

if __name__ == "__main__":
    get_all_products()
