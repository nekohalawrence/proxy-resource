import os
import yaml
import datetime
import re

# --- 配置区域 ---
SOURCE_DIR = 'rule/yaml'
TARGET_DIR = 'rule/list'

# 动态获取仓库信息
REPO_NAME = os.environ.get('GITHUB_REPOSITORY', 'User/proxy-resource')
BRANCH_NAME = os.environ.get('GITHUB_REF_NAME', 'main')

def ensure_dir(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)

def get_stats(payload):
    """统计规则类型数量"""
    stats = {}
    for line in payload:
        if isinstance(line, str) and line.strip().startswith('#'):
            continue
        rule = line if isinstance(line, str) else str(line)
        parts = rule.split(',')
        if parts and len(parts) > 0:
            rule_type = parts[0].strip()
            if rule_type and rule_type[0].isupper() and '-' in rule_type or rule_type.isupper():
                 stats[rule_type] = stats.get(rule_type, 0) + 1
    return stats

def extract_payload_categories(payload_str):
    """从 payload 字符串中提取注释作为类别"""
    categories = []
    lines = payload_str.splitlines()
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('#'):
            comment = stripped.lstrip('#').strip()
            if comment and not any(k in comment for k in ['DOMAIN', 'IP-', '规则计数', 'update_', 'name:', 'content:', 'repo:']):
                if comment not in categories:
                    categories.append(comment)
    return categories

def generate_header(original_header_lines, filename, ext, stats, categories):
    """
    生成标准化的文件头，严格控制空行。
    逻辑：构建三个独立的列表(Block)，最后用 \n\n 连接。
    """
    today = datetime.datetime.now().strftime('%Y%m%d')
    
    # 构建当前文件的目标路径
    if ext == '.yaml':
        relative_path = f"{SOURCE_DIR}/{filename}{ext}"
    else:
        relative_path = f"{TARGET_DIR}/{filename}{ext}"

    # 1. 构建【基础信息块】 (Block 1)
    base_lines = []
    
    # 状态标记：是否检测到字段
    has_date = False
    has_url = False
    has_repo = False
    
    # 状态标记：跳过旧的自动生成块
    skip_block = False

    for line in original_header_lines:
        stripped = line.strip()
        
        if stripped.startswith('payload:'):
            break

        # --- 跳过旧的统计/分类块 ---
        # 兼容两种样式的旧块：'# 包含的规则' / '# 规则计数' 和 '# -------规则列表-------' / '# -------规则计数-------'
        if any(k in stripped for k in ['包含的规则', '规则计数', '规则列表']):
            skip_block = True
            continue
        
        if skip_block:
            # 如果是空行，或者看起来像列表项(# xxx)，继续跳过
            if stripped == '' or (stripped.startswith('#') and ':' not in stripped) or (stripped.startswith('#') and ':' in stripped and not any(x in stripped for x in ['name:', 'content:', 'repo:', 'update_'])):
                continue
            else:
                skip_block = False
        if skip_block:
            continue

        # --- 更新动态字段 ---
        if stripped.startswith('# update_date:'):
            base_lines.append(f'# update_date: {today}')
            has_date = True
            continue
            
        if stripped.startswith('# update_url:'):
            new_url = f'https://raw.githubusercontent.com/{REPO_NAME}/{BRANCH_NAME}/{relative_path}'
            base_lines.append(f'# update_url: {new_url}')
            has_url = True
            continue

        if stripped.startswith('# repo:'):
            repo_url = f'https://github.com/{REPO_NAME}/tree/{BRANCH_NAME}/{os.path.dirname(relative_path)}'
            base_lines.append(f'# repo: {repo_url}')
            has_repo = True
            continue

        # 保留其他原有行
        base_lines.append(line)

    # 补全缺失字段
    if not has_date:
        base_lines.append(f'# update_date: {today}')
    if not has_url:
        new_url = f'https://raw.githubusercontent.com/{REPO_NAME}/{BRANCH_NAME}/{relative_path}'
        base_lines.append(f'# update_url: {new_url}')
    if not has_repo:
        repo_url = f'https://github.com/{REPO_NAME}/tree/{BRANCH_NAME}/{os.path.dirname(relative_path)}'
        base_lines.append(f'# repo: {repo_url}')

    # 清理 base_lines 尾部的空行，确保拼接时不会出现多余空行
    while base_lines and base_lines[-1].strip() == '':
        base_lines.pop()

    # 2. 构建【规则计数块】 (Block 2) — gfwlite 风格，放在前面并使用分隔线
    stat_lines = []
    if stats:
        stat_lines.append('# -------规则计数-------')
        for r_type, count in sorted(stats.items()):
            stat_lines.append(f'# {r_type}: {count}')

    # 3. 构建【规则列表块】 (Block 3) — gfwlite 风格的规则列表标题
    cat_lines = []
    if categories:
        cat_lines.append('# -------规则列表-------')
        for cat in categories:
            cat_lines.append(f'# {cat}')

    # --- 最终拼接 ---
    blocks = []
    if base_lines:
        blocks.append("\n".join(base_lines))
    # gfwlite 风格把规则计数放在规则列表之前
    if stat_lines:
        blocks.append("\n".join(stat_lines))
    if cat_lines:
        blocks.append("\n".join(cat_lines))

    final_header = "\n\n".join(blocks)
    return final_header + "\n\n"

def write_file_if_changed(path, content):
    """仅当内容变化时写入"""
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            old_content = f.read()
        if old_content.strip() == content.strip():
            print(f"  -> 内容无变化，跳过写入: {os.path.basename(path)}")
            return
    
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"  -> 已更新: {path}")

def process_file(filename):
    print(f"正在处理: {filename}")
    source_path = os.path.join(SOURCE_DIR, filename)
    filename_no_ext = os.path.splitext(filename)[0]
    
    with open(source_path, 'r', encoding='utf-8') as f:
        full_content = f.read()

    # --- 分离 Header 和 Payload ---
    if 'payload:' not in full_content:
        print(f"警告: {filename} 缺少 payload，跳过")
        return

    parts = full_content.split('payload:', 1)
    header_raw = parts[0]
    payload_raw = parts[1] # 包含原始缩进和注释

    # --- 解析数据用于统计 ---
    try:
        temp_payload = yaml.safe_load('payload:' + payload_raw)
        payload_list_clean = temp_payload.get('payload', [])
        if payload_list_clean is None: payload_list_clean = []
    except Exception as e:
        print(f"解析 YAML 结构失败: {e}")
        return

    stats = get_stats(payload_list_clean)
    categories = extract_payload_categories(payload_raw)

    # --- 生成新的 YAML 内容 ---
    # 先构建修改后的 payload（去除条目两端的单/双引号，同时保留注释和缩进）
    payload_lines = payload_raw.splitlines(True)  # 保留换行符
    modified_payload_lines = []
    # 匹配：前导空白和 '- '，可选的引号，值，可选的引号，可选内联注释
    item_re = re.compile(r'^(\s*-\s*)([\'\"]?)(.+?)([\'\"]?)(\s*(#.*))?(\r?\n)?$')
    for pl in payload_lines:
        if pl.strip() == '':
            modified_payload_lines.append(pl)
            continue
        if pl.lstrip().startswith('#'):
            # 注释行，保留原样
            modified_payload_lines.append(pl)
            continue
        m = item_re.match(pl)
        if m:
            leading = m.group(1)
            value = m.group(3)
            trailing_comment = m.group(5) or ''
            newline = '\n' if pl.endswith('\n') else ''
            if trailing_comment:
                # trailing_comment 含有前置空格和注释符号
                modified_payload_lines.append(f"{leading}{value}{trailing_comment}{newline}")
            else:
                modified_payload_lines.append(f"{leading}{value}{newline}")
        else:
            # 不是标准的 - item 行，原样保留
            modified_payload_lines.append(pl)

    modified_payload_raw = ''.join(modified_payload_lines)

    new_yaml_header = generate_header(header_raw.splitlines(), filename_no_ext, '.yaml', stats, categories)
    new_yaml_content = new_yaml_header + "payload:" + modified_payload_raw

    # --- 生成新的 LIST 内容 ---
    new_list_header = generate_header(header_raw.splitlines(), filename_no_ext, '.list', stats, categories)
    
    list_body_lines = []
    for line in modified_payload_raw.splitlines():
        stripped = line.strip()
        if not stripped: continue
        if stripped.startswith('- '):
            # 去掉 '- ' 和两端引号（如果有）
            item = stripped[2:].strip().strip('\'\"')
            list_body_lines.append(item)
        elif stripped.startswith('#'):
            list_body_lines.append(stripped)

    # 注意：List 文件通常不需要 "payload:" 关键字，直接接内容
    # generate_header 结尾有 \n\n，刚好分开 Header 和 Body
    new_list_content = new_list_header + "\n".join(list_body_lines) + "\n"

    # --- 写入文件 ---
    write_file_if_changed(source_path, new_yaml_content)
    
    target_path = os.path.join(TARGET_DIR, filename_no_ext + '.list')
    write_file_if_changed(target_path, new_list_content)

def main():
    if not os.path.exists(SOURCE_DIR):
        print(f"错误: 源目录 {SOURCE_DIR} 不存在")
        exit(1)
    ensure_dir(TARGET_DIR)

    files = [f for f in os.listdir(SOURCE_DIR) if f.endswith(('.yaml', '.yml'))]
    for file in files:
        process_file(file)

if __name__ == '__main__':
    main()
