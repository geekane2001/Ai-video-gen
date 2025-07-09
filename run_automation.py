import json
import re
from datetime import datetime
from playwright.sync_api import sync_playwright, Playwright, Page, Locator
import time
import base64
from openai import OpenAI
import os # 导入 os 库

# --- 配置 ---
TARGET_URL = "https://aic.oceanengine.com/tools/smart_clip/mixed/common?bpId=1768581378181123"
COOKIE_FILE_PATH = "即创.json" # Cookie 文件名保持不变
SEARCH_TERM = "电竞酒店装修板块素材"
DEFAULT_COPY_TEXT = (
    "玩家用脚投票的电竞馆，装修都有这些小心机：低蓝光照明保护视力，"
    "阶梯式观赛区无视线死角，隐藏式线缆让场地整洁到能拍宣传片。"
    "我们团队里一半是资深玩家，懂你要的热血更懂运营痛点，30 天从毛坯到营业，"
    "点击私信，免费出可行性装修报告！"
)
ACTION_TIMEOUT = 30000 

# --- 视觉大模型 (VLM) 配置 ---
# 【核心修改】从环境变量中读取密钥
MODELSCOPE_API_KEY = os.getenv("MODELSCOPE_API_KEY")
MODELSCOPE_BASE_URL = "https://api-inference.modelscope.cn/v1/"
VLM_MODEL_ID = "Qwen/Qwen2.5-VL-7B-Instruct"

def get_task_name_from_vlm(image_bytes: bytes) -> str | None:
    """调用视觉大模型从图片中提取任务名称。"""
    # ... 此函数无需修改 ...
    print("\n[INFO] 正在调用视觉大模型 (VLM) 进行识别...")
    try:
        if not MODELSCOPE_API_KEY:
            print("❌ [FAIL] 环境变量 MODELSCOPE_API_KEY 未设置！")
            return None
        client = OpenAI(base_url=MODELSCOPE_BASE_URL, api_key=MODELSCOPE_API_KEY)
        base64_image = base64.b64encode(image_bytes).decode('utf-8')
        data_url = f"data:image/png;base64,{base64_image}"
        prompt_text = "这张图片里有'任务名称：'，请只提取并返回'任务名称：'后面的全部内容，不要包含'任务名称：'这几个字，也不要任何其他描述或解释。"
        print("  - 正在向VLM发送请求...")
        response = client.chat.completions.create(
            model=VLM_MODEL_ID,
            messages=[{'role': 'user', 'content': [{'type': 'text', 'text': prompt_text}, {'type': 'image_url', 'image_url': {'url': data_url}}]}],
            stream=False
        )
        task_name = response.choices[0].message.content.strip()
        print(f"  - VLM 返回结果: '{task_name}'")
        return task_name
    except Exception as e:
        print(f"❌ [FAIL] 调用视觉大模型失败！")
        print(f"  - 失败原因: {type(e).__name__}: {e}")
        return None

def safe_action(page: Page, locator: Locator, action_name: str, action_type: str, value: str = None, **kwargs) -> bool:
    """安全操作函数"""
    # ... 此函数无需修改 ...
    print(f"\n[INFO] 准备执行: {action_name}")
    try:
        if not kwargs.get("force"):
            print(f"  - 等待元素可见...")
            locator.wait_for(state="visible", timeout=kwargs.get('timeout', ACTION_TIMEOUT))
            print(f"  - 元素已可见。")
        kwargs['timeout'] = kwargs.get('timeout', ACTION_TIMEOUT)
        if action_type == 'click':
            if kwargs.get("force"): print(f"  - 正在强制点击 (忽略按钮状态)...")
            else: print(f"  - 正在等待并点击...")
            locator.click(**kwargs)
        elif action_type == 'fill':
            print(f"  - 正在输入文本: '{value[:30]}...'")
            locator.fill(value, **kwargs)
        elif action_type == 'press':
            print(f"  - 正在按下按键: '{value}'")
            locator.press(value, **kwargs)
        else: return False
        print(f"[SUCCESS] 成功完成: {action_name}")
        time.sleep(1) 
        return True
    except Exception as e:
        print(f"❌ [FAIL] 执行 '{action_name}' 失败！")
        safe_action_name = re.sub(r'[\\/*?:"<>|]', "", action_name)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_path = f"error_{timestamp}_{safe_action_name[:50]}.png"
        try:
            page.screenshot(path=screenshot_path, full_page=True)
            print(f"  - 📸 错误快照已保存至: {screenshot_path}")
        except Exception as se: print(f"  - 📸 尝试截图失败: {se}")
        print(f"  - 失败原因: {type(e).__name__}: {e}")
        return False

def run(playwright: Playwright):
    """主执行函数"""
    print("自动化脚本启动...")
    # 在 GitHub Actions 中，Playwright 需要以无头模式运行
    browser = playwright.chromium.launch(headless=True) 
    context = browser.new_context()
    page = context.new_page()

    try:
        # --- 步骤 1-4 保持不变 ---
        with open(COOKIE_FILE_PATH, 'r') as f: cookies = json.load(f)
        for cookie in cookies:
            if 'expirationDate' in cookie: cookie['expires'] = cookie.pop('expirationDate')
            if 'sameSite' in cookie:
                if cookie['sameSite'] == 'no_restriction': cookie['sameSite'] = 'None'
                elif cookie['sameSite'] not in ['Lax', 'Strict', 'None']: cookie['sameSite'] = 'Lax'
        context.add_cookies(cookies)
        page.goto(TARGET_URL, timeout=60000, wait_until="domcontentloaded")
        try:
            page.get_by_role("button", name="同意登录").wait_for(state="visible", timeout=5000)
            if not safe_action(page, page.get_by_text("我已阅读并同意即创平台服务协议、即创隐私政策"), "勾选'我已阅读并同意'", 'click', position={'x': 10, 'y': 10}): raise
            if not safe_action(page, page.get_by_role("button", name="同意登录"), "点击'同意登录'按钮", 'click'): raise
            page.wait_for_load_state("networkidle", timeout=ACTION_TIMEOUT)
        except Exception: print("[INFO] 未检测到登录确认对话框或已处理。")
        if not safe_action(page, page.get_by_text("添加视频或商品图"), "点击'添加视频或商品图'", 'click'): raise
        search_box_locator = page.get_by_role("textbox", name="在 原料库 中搜索")
        if not safe_action(page, search_box_locator, f"输入搜索词'{SEARCH_TERM}'", 'fill', value=SEARCH_TERM): raise
        if not safe_action(page, search_box_locator, "执行搜索(按回车键)", 'press', value='Enter'): raise
        page.wait_for_load_state("networkidle", timeout=ACTION_TIMEOUT)
        result_name_identifier = f"{SEARCH_TERM} - j***2@163.com"
        if not safe_action(page, page.get_by_role("row", name=result_name_identifier).locator("label div").nth(1), f"点击搜索结果'{result_name_identifier}'", 'click'): raise
        
        # --- 步骤 5 ---
        if not safe_action(page, page.get_by_role("button", name="确定"), "点击'确定'按钮", 'click'): raise
        
        # 【核心修改】从环境变量中获取自定义文本，如果不存在则使用默认文本
        final_copy_text = os.getenv("CUSTOM_TEXT", DEFAULT_COPY_TEXT)
        print(f"[INFO] 使用文案: '{final_copy_text[:50]}...'")

        if not safe_action(page, page.get_by_role("paragraph"), "在文案框输入文本", 'fill', value=final_copy_text): raise

        # --- 步骤 6 ---
        generate_button_locator = page.get_by_role("button", name="立即生成")
        if not safe_action(page, generate_button_locator, "强制点击'立即生成'以触发审核", 'click', force=True): raise
        print("\n[INFO] 文案已提交审核，正在等待 '立即生成' 按钮再次变为可点击状态...")
        if not safe_action(page, generate_button_locator, "等待并点击'立即生成'以完成创建", 'click'): raise
        
        # --- 步骤 7 ---
        print("\n[INFO] 等待 2 秒，确保生成动画和UI稳定...")
        time.sleep(2)
        print("\n[INFO] 正在对当前整个页面进行截图...")
        try:
            vlm_screenshot_path = "vlm_input_image.png"
            screenshot_bytes = page.screenshot(path=vlm_screenshot_path)
            print(f"  - 页面截图已保存至: {vlm_screenshot_path}")
            
            extracted_name = get_task_name_from_vlm(screenshot_bytes)
            
            if extracted_name:
                print("\n" + "="*60)
                print(f"✅ [SUCCESS] VLM 成功提取任务信息！")
                print(f"  - 任务名称： {extracted_name}")
                print("="*60)
                # 【核心修改】将任务名称输出，以便 GitHub Actions 捕获
                with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
                    print(f'task_name={extracted_name}', file=f)
            else:
                print("\n" + "⚠️ [WARNING] VLM 未能成功提取任务名称。")
        except Exception as e:
            print(f"❌ [FAIL] 截图或调用VLM时失败！")
            page.screenshot(path=f"error_{datetime.now().strftime('%Y%m%d_%H%M%S')}_vlm_failed.png", full_page=True)
            print(f"  - 失败原因: {type(e).__name__}: {e}")
            
    except Exception as e:
        print(f"\n[CRITICAL] 脚本因流程中的关键错误提前终止: {e}")
    finally:
        print("正在关闭浏览器...")
        browser.close()

def main():
    with sync_playwright() as playwright:
        run(playwright)
    print("脚本执行完毕。")

if __name__ == "__main__":
    main()
