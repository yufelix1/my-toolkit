import os
import hashlib
import bencodepy
import glob
from datetime import datetime
from flask import Blueprint, request, render_template, send_from_directory, jsonify

torrent_to_magnet_bp = Blueprint('torrent_to_magnet', __name__, template_folder='../../templates/torrent_to_magnet')

INPUT_DIR = os.getenv('INPUT_DIR', '/torrents')
OUTPUT_DIR = os.getenv('OUTPUT_DIR', '/output')

os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

def torrent_to_magnet(torrent_path):
    try:
        with open(torrent_path, 'rb') as f:
            metadata = bencodepy.bdecode(f.read())
        info = metadata[b'info']
        info_bencoded = bencodepy.bencode(info)
        info_hash = hashlib.sha1(info_bencoded).hexdigest().lower()
        return f"magnet:?xt=urn:btih:{info_hash}"
    except Exception as e:
        print(f"转换失败 {torrent_path}: {e}")
        return None

def clear_torrents():
    torrent_files = glob.glob(os.path.join(INPUT_DIR, '**', '*.torrent'), recursive=True)
    for t in torrent_files:
        try:
            os.remove(t)
        except Exception as e:
            print(f"删除失败 {t}: {e}")

@torrent_to_magnet_bp.route('/')
def index():
    return render_template('torrent_to_magnet/index.html')   # ← 这里已修正

@torrent_to_magnet_bp.route('/upload', methods=['POST'])
def upload():
    if 'files' not in request.files:
        return jsonify({"error": "没有文件"}), 400
    files = request.files.getlist('files')
    uploaded = 0
    for file in files:
        if file and file.filename.lower().endswith('.torrent'):
            file.save(os.path.join(INPUT_DIR, file.filename))
            uploaded += 1
    return jsonify({
        "success": True,
        "message": f"✅ 成功上传 {uploaded} 个 torrent 文件"
    })

@torrent_to_magnet_bp.route('/convert', methods=['POST'])
def convert():
    torrent_files = glob.glob(os.path.join(INPUT_DIR, '**', '*.torrent'), recursive=True)
    magnets = []
    for t in torrent_files:
        magnet = torrent_to_magnet(t)
        if magnet:
            magnets.append(magnet)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(OUTPUT_DIR, f"magnets_{timestamp}.txt")
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("\n".join(magnets))

    clear_torrents()

    return jsonify({
        "status": "success",
        "count": len(magnets),
        "file": os.path.basename(output_file)
    })

@torrent_to_magnet_bp.route('/download/<filename>')
def download(filename):
    return send_from_directory(OUTPUT_DIR, filename)