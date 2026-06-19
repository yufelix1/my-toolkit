from flask import Blueprint, render_template, request, jsonify
import os
import shutil
from datetime import datetime

flatten_bp = Blueprint('flatten', __name__, template_folder='../../templates/flatten')

def do_flatten(target_dir):
    if not os.path.isdir(target_dir):
        return {"success": False, "message": f"路径不存在或不是目录：{target_dir}"}

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    new_dir = os.path.join(target_dir, timestamp)
    os.makedirs(new_dir, exist_ok=True)

    moved_count = 0
    for item in os.listdir(target_dir):
        item_path = os.path.join(target_dir, item)
        if os.path.isdir(item_path):
            for file_name in os.listdir(item_path):
                file_path = os.path.join(item_path, file_name)
                if os.path.isfile(file_path):
                    dest_path = os.path.join(new_dir, file_name)
                    # 处理文件名冲突
                    if os.path.exists(dest_path):
                        base, ext = os.path.splitext(file_name)
                        counter = 1
                        while os.path.exists(dest_path):
                            dest_path = os.path.join(new_dir, f"{base}_{counter}{ext}")
                            counter += 1
                    shutil.move(file_path, dest_path)
                    moved_count += 1
            # 尝试删除空目录
            try:
                os.rmdir(item_path)
            except OSError:
                pass
    return {
        "success": True,
        "message": f"操作完成！\n移动文件数量：{moved_count}\n新目录：{new_dir}"
    }

@flatten_bp.route('/')
def index():
    return render_template('flatten/index.html')

@flatten_bp.route('/api', methods=['POST'])
def api():
    data = request.get_json()
    target_dir = data.get('path', '').strip()
    if not target_dir:
        return jsonify({"success": False, "message": "请输入目录路径"})
    result = do_flatten(target_dir)
    return jsonify(result)