from openai import OpenAI

client = OpenAI(
    api_key="sk-04ca03e32d7d44f4b90f52ef3cd58b71",  # key của bạn
    base_url="https://api.deepseek.com"
)
print("Base URL:", client.base_url)
try:
    # Đổi sang tên model mới
    response = client.chat.completions.create(
        model="deepseek-flash", 
        messages=[{"role": "user", "content": "Xin chào, viết cho tôi hàm tính tổng trong Python"}]
    )
    print("THÀNH CÔNG:", response.choices[0].message.content)
except Exception as e:
    print("LỖI:", e)