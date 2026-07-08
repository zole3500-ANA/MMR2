# -*- coding: utf-8 -*-
"""
ระบบดึงข้อมูลจาก HDC API เพื่ออัพเดทรายงานผลงานความครอบคลุมวัคซีน MMR2 อัตโนมัติ
================================================================
วิธีใช้:
  1. รัน: uv run sync_hdc_mmr2.py
"""

import os
import re
import sys
import io
import urllib.request
import json
import subprocess

# Set output encoding to UTF-8 to prevent encoding errors on Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def find_git_exe():
    import shutil
    git_path = shutil.which('git')
    if git_path:
        return git_path
    standard_paths = [
        r"C:\Program Files\Git\cmd\git.exe",
        r"C:\Program Files (x86)\Git\cmd\git.exe",
    ]
    userprofile = os.environ.get('USERPROFILE', '')
    if userprofile:
        github_desktop_dir = os.path.join(userprofile, r"AppData\Local\GitHubDesktop")
        if os.path.exists(github_desktop_dir):
            for root, dirs, files in os.walk(github_desktop_dir):
                if 'git.exe' in files:
                    return os.path.join(root, 'git.exe')
    for p in standard_paths:
        if os.path.exists(p):
            return p
    return "git"

def find_repo_dir(repo_name):
    # Check script directory and parent directory first (for GitHub Actions / portable runs)
    if os.path.isdir(os.path.join(SCRIPT_DIR, '.git')):
        return SCRIPT_DIR
    parent_dir = os.path.dirname(SCRIPT_DIR)
    if os.path.isdir(os.path.join(parent_dir, '.git')):
        return parent_dir
        
    paths_to_check = [
        os.path.join(r"C:\GitRepos", repo_name),
    ]
    userprofile = os.environ.get('USERPROFILE', '')
    if userprofile:
        paths_to_check.extend([
            os.path.join(userprofile, "OneDrive", "เอกสาร", "GitHub", repo_name),
            os.path.join(userprofile, "OneDrive", "Documents", "GitHub", repo_name),
            os.path.join(userprofile, "Documents", "GitHub", repo_name),
            os.path.join(userprofile, repo_name),
            os.path.join(r"C:\Users\zole3", repo_name),
        ])
    for p in paths_to_check:
        if os.path.exists(p) and os.path.isdir(os.path.join(p, '.git')):
            return p
    return None

# Find paths dynamically
GIT_EXE = find_git_exe()
GIT_DIR = find_repo_dir('MMR2')
if not GIT_DIR:
    print("❌ ไม่พบโฟลเดอร์ Git Repository ของ MMR2")
    sys.exit(1)

HTML_PATH = os.path.join(GIT_DIR, 'dashboard.html')
PUSH_TO_GITHUB = True

def fetch_hdc_data():
    print("🌐 กำลังดึงข้อมูลจาก HDC API...")
    exchange_id = "71e49e4b61aafee17761601c506d5f85"
    url = f"https://api-hdc.moph.go.th/v1/reports/province/data/{exchange_id}?table_display=provider&year=2569&month=ALL&zone=07&province_code=46&district_code=ALL&subdistrict_code=ALL&department_code=ALL&organization_type=ALL&ministry=ALL&hospital=ALL&service_plan=ALL&jurisdiction_code=ALL&freeze_month=ALL&mental_code=ALL&mental_group_code=ALL&custom=[]"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'domain': 'ksn',
        'authorization': 'Bearer null',
        'referer': 'https://hdc.moph.go.th/',
        'accept': 'application/json, text/plain, */*'
    }
    
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as r:
            res_content = r.read().decode('utf-8')
            data_json = json.loads(res_content)
            
            if not data_json.get('ok'):
                print("❌ HDC API ตอบกลับผลลัพธ์เป็นเท็จ (ok: false)")
                sys.exit(1)
                
            rows = data_json.get('rows', [])
            if not rows:
                print("❌ ไม่พบข้อมูล rows ในการตอบกลับของ HDC API")
                sys.exit(1)
                
            datecom = rows[0].get('datecom', 'ไม่ทราบวันที่')
            inner_data = rows[0].get('data', [])
            print(f"✅ ดึงข้อมูลสำเร็จ! พบรายการข้อมูล ณ วันที่ {datecom} จำนวน {len(inner_data)} รายการ")
            return datecom, inner_data
            
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในการเรียกใช้ HDC API: {e}")
        sys.exit(1)

def parse_existing_metadata():
    print(f"📂 อ่านข้อมูลโฮสต์ตั้งต้นจาก dashboard.html...")
    if not os.path.exists(HTML_PATH):
        print(f"❌ ไม่พบไฟล์: {HTML_PATH}")
        sys.exit(1)
        
    with open(HTML_PATH, 'r', encoding='utf-8') as f:
        html_content = f.read()
        
    match = re.search(r'const rawData = `([\s\S]*?)`;', html_content)
    if not match:
        print("❌ ไม่พบตัวแปร const rawData ในไฟล์ HTML")
        sys.exit(1)
        
    raw_data_block = match.group(1).strip()
    metadata_map = {}
    
    for line in raw_data_block.split('\n'):
        line = line.strip()
        if not line:
            continue
        parts = line.split(',')
        if len(parts) >= 7:
            try:
                idx = int(parts[0])
            except ValueError:
                idx = 999
            district = parts[1].strip()
            unit_full = parts[2].strip()
            agency = parts[3].strip()
            
            # Hospcode is the prefix of unit_full (before colon)
            if ':' in unit_full:
                hospcode = unit_full.split(':')[0].strip()
            else:
                hospcode = unit_full
                
            metadata_map[hospcode] = (idx, district, unit_full, agency)
            
    print(f"✅ ดึงเมตาดาต้าเดิมของหน่วยบริการสำเร็จ ({len(metadata_map)} แห่ง)")
    return metadata_map

def generate_new_raw_data(inner_data, metadata_map):
    print("📊 กำลังสแกนและประมวลผลข้อมูลรายหน่วยบริการ...")
    rows_data = []
    
    for item in inner_data:
        a_code = item.get('a_code', '').strip()
        if not a_code:
            continue
            
        t1 = int(float(item.get('targetq1', 0))) if item.get('targetq1') is not None else 0
        t2 = int(float(item.get('targetq2', 0))) if item.get('targetq2') is not None else 0
        t3 = int(float(item.get('targetq3', 0))) if item.get('targetq3') is not None else 0
        target = t1 + t2 + t3
        
        m1 = int(float(item.get('mmr2q1', 0))) if item.get('mmr2q1') is not None else 0
        m2 = int(float(item.get('mmr2q2', 0))) if item.get('mmr2q2') is not None else 0
        m3 = int(float(item.get('mmr2q3', 0))) if item.get('mmr2q3') is not None else 0
        mmr2 = m1 + m2 + m3
        
        # Calculate percent
        if target > 0:
            percent = round((mmr2 / target) * 100, 2)
        else:
            percent = 0.00
            
        if percent == int(percent):
            percent_str = str(int(percent))
        else:
            percent_str = f"{percent:.2f}"
            
        # Get metadata mapping
        if a_code in metadata_map:
            idx, district, unit_full, agency = metadata_map[a_code]
        else:
            # New unit fallback
            idx = 999
            district = ""
            a_name = item.get('a_name', '').strip()
            if ':' in a_name:
                unit_name_clean = a_name.split(':')[1].strip()
            else:
                unit_name_clean = a_name
            unit_full = f"{a_code}:{unit_name_clean}"
            agency = "สำนักงานสาธารณสุขจังหวัด"
            
        rows_data.append((idx, district, unit_full, agency, target, mmr2, percent_str))
        
    # Sort by original idx
    rows_data.sort(key=lambda x: x[0])
    
    # Format as string
    formatted_lines = []
    for r in rows_data:
        formatted_lines.append(f"{r[0]},{r[1]},{r[2]},{r[3]},{r[4]},{r[5]},{r[6]}")
        
    new_raw_data_str = "\n".join(formatted_lines)
    return new_raw_data_str

def update_html(datecom, new_raw_data_str):
    print(f"📝 แก้ไขไฟล์ dashboard.html...")
    with open(HTML_PATH, 'r', encoding='utf-8') as f:
        html_content = f.read()
        
    subtitle = f"จังหวัดกาฬสินธุ์ | ไตรมาสที่ 1-3 (ข้อมูล ณ วันที่ {datecom})"
    
    # Replace date subtitle
    new_html = re.sub(
        r'<p>จังหวัดกาฬสินธุ์ \| ไตรมาสที่ [^<]+ \(ข้อมูล ณ วันที่ [^<]+\)</p>',
        f'<p>{subtitle}</p>',
        html_content
    )
    
    # Replace rawData
    new_html = re.sub(
        r'const rawData = `[\s\S]*?`;',
        f'const rawData = `{new_raw_data_str}`;',
        new_html
    )
    
    with open(HTML_PATH, 'w', encoding='utf-8') as f:
        f.write(new_html)
        
    print("✅ เขียนไฟล์สำเร็จ!")
    return datecom

def run_git(datecom):
    if not os.path.exists(GIT_EXE):
        print(f"❌ ไม่พบ git.exe ที่ {GIT_EXE}")
        return
        
    print(f"🚀 กำลังส่งออกข้อมูลขึ้น GitHub ที่: {GIT_DIR}")
    try:
        # git add
        subprocess.run([GIT_EXE, 'add', 'dashboard.html'], cwd=GIT_DIR, check=True)
        # git commit
        commit_msg = f"Auto-update MMR2 from HDC API (ข้อมูล ณ วันที่ {datecom})"
        subprocess.run([GIT_EXE, 'commit', '-m', commit_msg], cwd=GIT_DIR, capture_output=True)
        # git push
        subprocess.run([GIT_EXE, 'push', 'origin', 'main'], cwd=GIT_DIR, check=True)
        print("🎉 ดันข้อมูลขึ้น GitHub Pages เรียบร้อยแล้ว!")
        print("🔗 https://zole3500-ana.github.io/MMR2/dashboard.html")
    except Exception as e:
        print(f"❌ มีข้อผิดพลาดในการดำเนินการ Git: {e}")

def main():
    print("="*60)
    print("  ระบบดึงข้อมูล HDC อัตโนมัติและอัพเดท MMR2 แดชบอร์ด")
    print("="*60)
    
    datecom, inner_data = fetch_hdc_data()
    metadata_map = parse_existing_metadata()
    new_raw_data_str = generate_new_raw_data(inner_data, metadata_map)
    update_html(datecom, new_raw_data_str)
    
    if PUSH_TO_GITHUB:
        run_git(datecom)
        
    print("="*60)
    print("  ดำเนินการสำเร็จเรียบร้อย!")
    print("="*60)

if __name__ == '__main__':
    main()
