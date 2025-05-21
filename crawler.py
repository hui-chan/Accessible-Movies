import json
import os
import random
import time
import traceback

import requests
from pypinyin import Style, pinyin
from pyquery import PyQuery as pq
from selenium import webdriver
from selenium.common.exceptions import ElementClickInterceptedException
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options
from selenium.webdriver.edge.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.microsoft import EdgeChromiumDriverManager


def setup_browser():
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0")
    service = Service(EdgeChromiumDriverManager().install())
    driver = webdriver.Edge(service=service, options=options)

    # 防检测
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', { get: () => undefined })"
    })
    return driver

def baidu_search(driver, keyword):
    url = f"https://www.baidu.com/s?wd={keyword}+百度百科"
    driver.get(url)
    time.sleep(random.uniform(1.5, 3.5))

    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'h3 a'))
        )
        links = driver.find_elements(By.CSS_SELECTOR, 'h3 a')
        result_list = [(i, a.text.strip(), a.get_attribute('href')) for i, a in enumerate(links) if a.text]
        for idx, title, href in result_list:
            print(f"[{idx}] {title[:40]} -> {href}")
        return result_list
        # ###########################################
        # choice = int(input("请输入你想进入的编号："))
        # return result_list[choice][2]
        # #######################################
    except:
        print("[ERROR] 百度搜索加载失败或无有效结果。")
        return None

def try_click_expand(driver):
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '[class^="showAll_"]'))
        )
        expand_button = driver.find_element(By.CSS_SELECTOR, '[class^="showAll_"]')
        for attempt in range(5):
            try:
                driver.execute_script("arguments[0].scrollIntoView({behavior: 'instant', block: 'center'});", expand_button)
                time.sleep(0.8)
                expand_button.click()
                print("[INFO] 成功点击了展开按钮。")
                time.sleep(2)
                return True
            except ElementClickInterceptedException:
                print(f"[WARN] 展开按钮被遮挡，重试第{attempt + 1}次...")
                driver.execute_script("window.scrollBy(0, -100)")
                time.sleep(1)
        print("[WARN] 展开按钮多次尝试后仍无法点击。")
        return False
    except Exception as e:
        print(f"[WARN] 展开按钮查找失败：{e}")
        return False
    
def crawl_baike_roles_images(driver, character_image_dir, baike_url,expanded):
    os.makedirs(character_image_dir, exist_ok=True)

    print(f"[INFO] 正在访问词条：{baike_url}")
    driver.get(baike_url)

    if expanded:try_click_expand(driver)

    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '[class^="roleItem_"]'))
        )

        # 滚动页面确保图片加载
        for _ in range(3):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1.5)

        WebDriverWait(driver, 15).until(
            lambda d: all(img.get_attribute('src') for img in d.find_elements(By.CSS_SELECTOR, '[class^="roleItem_"] img'))
        )

    except:
        print("[WARN] 页面可能没有角色模块或图片未加载完全。")

    html = driver.page_source
    doc = pq(html)
    cast_list = []
    role_list = []

    roles = list(doc('[class^="roleItem_"]').items())
    for role_item in roles:
        role_name = role_item.find('[class^="roleName_"]').find('[class^="text"]').text().strip()
        role_name_pinyin_list=pinyin(role_name,style=Style.NORMAL)
        role_name_pinyin = "".join([item[0] for item in role_name_pinyin_list])
        img_url = role_item.find('img').attr('src')

        if img_url and role_name_pinyin:
            try:
                headers = {'User-Agent': 'Mozilla/5.0'}
                response = requests.get(img_url, headers=headers, timeout=20)
                response.raise_for_status()

                file_name = f"{role_name_pinyin}.png".replace('/', '_').replace('\\', '_')
                save_path = os.path.join(character_image_dir, file_name)
                with open(save_path, 'wb') as f:
                    f.write(response.content)

                print(f"[INFO] 图片已保存：{save_path}")
                cast_list.append({"role": role_name, "image_path": save_path})
                role_list.append(f"{role_name_pinyin},{role_name}\n")
            except Exception as e:
                print(f"[WARN] 下载失败：{role_name} -> {e}")
        else:
            print(f"[WARN] 跳过无效角色信息。")

    json_path = os.path.join(character_image_dir, f"info.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(cast_list, f, ensure_ascii=False, indent=4)
    
    txt_path=os.path.join(character_image_dir, "zh.txt")
    if not expanded:
        with open(txt_path,'w',encoding='utf-8') as txtfile:
            txtfile.writelines(role_list)
    else:
        with open(txt_path,'a',encoding='utf-8') as txtfile:
            txtfile.writelines(role_list)

    print(f"[INFO] 全部角色信息已保存：{json_path}")

if __name__ == '__main__':
    movie = input("请输入电影/电视剧名称：").strip()
    driver = setup_browser()

    try:
        url = baidu_search(driver, movie)
        if url:
            crawl_baike_roles_images(driver, movie, url,False)
            crawl_baike_roles_images(driver, movie, url,True)
        else:
            print("[ERROR] 没有有效词条可用，程序终止。")

    except Exception as e:
        print(f"[ERROR] 程序出错：{e}")
        traceback.print_exc()

    finally:
        driver.quit()
        print("[INFO] 浏览器已关闭。")
