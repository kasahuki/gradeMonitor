import os
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

import asyncio
import json
import requests
from playwright.async_api import async_playwright
import easyocr

# 配置（从环境变量读取）
USERNAME = os.environ.get("JW_USERNAME", "")
PASSWORD = os.environ.get("JW_PASSWORD", "")
FEISHU_WEBHOOK = os.environ.get("FEISHU_WEBHOOK", "")
LOGIN_URL = "http://jwgl.fafu.edu.cn/"
GRADES_FILE = "grades_cache.json"

reader = None

def get_reader():
    global reader
    if reader is None:
        reader = easyocr.Reader(['en'], gpu=False)
    return reader

import re

async def get_captcha_image(page):
    """获取验证码图片"""
    try:
        img = page.locator('img#icode')
        await img.wait_for(state='visible', timeout=5000)
        
        # 方法1: 检查是否是 base64 图片
        src = await img.get_attribute('src')
        if src and src.startswith('data:image'):
            import base64
            # 格式: data:image/png;base64,xxxxx
            base64_data = src.split(',', 1)[1]
            return base64.b64decode(base64_data)
        
        # 方法2: 直接用 Playwright 截图验证码元素
        screenshot = await img.screenshot()
        if screenshot and len(screenshot) > 100:
            return screenshot
        
        # 方法3: 用 page.request 下载（保持 session）
        if src:
            if src.startswith('/'):
                from urllib.parse import urljoin
                img_url = urljoin(page.url, src)
            elif not src.startswith('http'):
                base_url = page.url.rsplit('/', 1)[0]
                img_url = f"{base_url}/{src}"
            else:
                img_url = src
            
            response = await page.request.get(img_url)
            if response.ok:
                return await response.body()
        
        return None
    except Exception as e:
        print(f"获取验证码失败: {e}")
        return None

def recognize_captcha(img_bytes):
    # 验证图片数据有效性
    if not img_bytes or len(img_bytes) < 100:
        print(f"验证码图片数据无效，大小: {len(img_bytes) if img_bytes else 0} bytes")
        return None
    
    # 检查是否为有效的图片格式（PNG/JPEG/GIF 头部）
    if not (img_bytes[:8] == b'\x89PNG\r\n\x1a\n' or  # PNG
            img_bytes[:2] == b'\xff\xd8' or           # JPEG
            img_bytes[:6] in (b'GIF87a', b'GIF89a')): # GIF
        print("验证码图片格式无效")
        return None
    
    with open("temp_captcha.png", "wb") as f:
        f.write(img_bytes)
    
    try:
        result = get_reader().readtext("temp_captcha.png", detail=0)
        if result:
            # 清理识别结果：只保留字母和数字，取前4位
            text = ''.join(result).replace(' ', '')
            text = re.sub(r'[^a-zA-Z0-9]', '', text)
            return text[:4] if len(text) >= 4 else None
    except Exception as e:
        print(f"OCR识别异常: {e}")
    return None

def load_grades():
    if os.path.exists(GRADES_FILE):
        with open(GRADES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_grades(grades):
    with open(GRADES_FILE, 'w', encoding='utf-8') as f:
        json.dump(grades, f, ensure_ascii=False, indent=2)

def send_feishu_notification(new_grades):
    """发送飞书通知"""
    if not FEISHU_WEBHOOK:
        print("未配置飞书 webhook，跳过通知")
        return
    
    content = "🎉 发现新成绩：\n\n"
    for g in new_grades:
        content += f"📚 {g['课程名称']}\n"
        content += f"   成绩: {g['成绩']} | 学分: {g['学分']}\n\n"
    
    payload = {
        "msg_type": "text",
        "content": {"text": content}
    }
    
    try:
        resp = requests.post(FEISHU_WEBHOOK, json=payload, timeout=10)
        if resp.status_code == 200:
            print("✅ 飞书通知发送成功")
        else:
            print(f"❌ 飞书通知失败: {resp.text}")
    except Exception as e:
        print(f"❌ 飞书通知异常: {e}")

async def check_grades():
    if not USERNAME or not PASSWORD:
        print("❌ 未配置用户名或密码")
        return
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # 登录
        for attempt in range(10):  # 增加到10次
            print(f"\n=== 登录尝试 {attempt + 1} ===")
            await page.goto(LOGIN_URL)
            await page.wait_for_timeout(1500)
            
            captcha_img = await get_captcha_image(page)
            if not captcha_img:
                print("获取验证码图片失败")
                continue
            code = recognize_captcha(captcha_img)
            print(f"识别验证码: {code}")
            
            if not code:
                continue
            
            await page.fill('#txtUserName', USERNAME)
            await page.fill('#TextBox2', PASSWORD)
            await page.fill('#txtSecretCode', code)
            await page.click('#RadioButtonList1_2')
            await page.click('#Button1')
            await page.wait_for_timeout(2000)
            
            # 打印当前URL和页面标题，帮助调试
            print(f"当前URL: {page.url}")
            title = await page.title()
            print(f"页面标题: {title}")
            
            # 检查是否有错误提示
            try:
                error_msg = await page.locator('script').all_text_contents()
                for msg in error_msg:
                    if 'alert' in msg:
                        print(f"页面提示: {msg[:100]}")
            except:
                pass
            
            if "xs_main" in page.url:
                print("✅ 登录成功!")
                break
        else:
            print("❌ 登录失败")
            await browser.close()
            return
        
        # 进入成绩查询页面
        print("\n进入成绩查询页面...")
        await page.click('text=信息查询')
        await page.wait_for_timeout(500)
        await page.click('text=成绩查询')
        await page.wait_for_timeout(3000)
        
        # 切换到 iframe
        frames = page.frames
        frame = frames[1] if len(frames) > 1 else page
        
        # 直接点击查询
        print("\n点击查询...")
        buttons = await frame.query_selector_all('input[type="submit"], input[type="button"], button')
        for btn in buttons:
            value = await btn.get_attribute('value')
            if value and '查' in value:
                await btn.click()
                break
        
        await page.wait_for_timeout(2000)
        
        # 解析成绩表格
        print("\n解析成绩...")
        rows = await frame.query_selector_all('table#Datagrid1 tr')
        
        current_grades = []
        for i, row in enumerate(rows):
            if i == 0:
                continue
            cells = await row.query_selector_all('td')
            if len(cells) >= 8:
                grade = {
                    '学年': await cells[0].inner_text(),
                    '学期': await cells[1].inner_text(),
                    '课程代码': await cells[2].inner_text(),
                    '课程名称': await cells[3].inner_text(),
                    '课程性质': await cells[4].inner_text(),
                    '课程归属': await cells[5].inner_text(),
                    '学分': await cells[6].inner_text(),
                    '成绩': await cells[7].inner_text()
                }
                current_grades.append(grade)
        
        # 检查新成绩
        saved_grades = load_grades()
        saved_keys = {f"{g['课程代码']}_{g['学年']}_{g['学期']}" for g in saved_grades}
        
        new_grades = []
        for g in current_grades:
            key = f"{g['课程代码']}_{g['学年']}_{g['学期']}"
            if key not in saved_keys:
                new_grades.append(g)
        
        if new_grades:
            print("\n🎉 发现新成绩:")
            for g in new_grades:
                print(f"  {g['课程名称']}: {g['成绩']} (学分:{g['学分']})")
            save_grades(current_grades)
            send_feishu_notification(new_grades)
        else:
            print("\n无新成绩")
        
        print(f"\n当前共 {len(current_grades)} 门课程成绩")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(check_grades())
