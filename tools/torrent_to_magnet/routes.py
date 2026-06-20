import os
import hashlib
import bencodepy
import glob
from datetime import datetime
from flask import Blueprint, request, render_template, send_from_directory, jsonify
import requests
import feedparser

torrent_to_magnet_bp = Blueprint('torrent_to_magnet', __name__, template_folder='../../templates/torrent_to_magnet')

INPUT_DIR = os.getenv('INPUT_DIR', '/data/torrents')
OUTPUT_DIR = os.getenv('OUTPUT_DIR', '/data/output')

os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

def torrent_to_magnet(torrent_path):
    try:
        with open(torrent_path, 'rb') as f:
            metadata = bencodepy.decode(f.read())
        info = metadata[b'info']
        info_bencoded = bencodepy.encode(info)
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

def download_from_rss(rss_url, filters=""):
    try:
        feed = feedparser.parse(rss_url)
        filter_list = [f.strip().lower() for f in filters.split(',') if f.strip()] if filters else []
        
        downloaded = 0
        skipped = 0
        
        for entry in feed.entries:
            title = entry.get('title', '')
            torrent_url = None
            
            # 获取 torrent 下载链接
            if 'enclosures' in entry and entry.enclosures:
                for enc in entry.enclosures:
                    if enc.get('type') == 'application/x-bittorrent' or enc.href.endswith('.torrent'):
                        torrent_url = enc.href
                        break
            elif 'link' in entry and entry.link.endswith('.torrent'):
                torrent_url = entry.link

            if not torrent_url:
                continue

            # 过滤
            if any(keyword in title.lower() for keyword in filter_list):
                skipped += 1
                continue

            # 下载
            try:
                resp = requests.get(torrent_url, timeout=30)
                if resp.status_code == 200:
                    filename = os.path.basename(torrent_url.split('?')[0]) or f"{hashlib.md5(title.encode()).hexdigest()[:8]}.torrent"
                    save_path = os.path.join(INPUT_DIR, filename)
                    with open(save_path, 'wb') as f:
                        f.write(resp.content)
                    downloaded += 1
            except Exception as e:
                print(f"下载失败 {torrent_url}: {e}")

        return {
            "success": True,
            "message": f"✅ RSS 处理完成！\n成功下载: {downloaded} 个种子\n跳过（过滤）: {skipped} 个\n目录: {INPUT_DIR}"
        }
    except Exception as e:
        return {"success": False, "message": f"RSS 下载失败: {str(e)}"}

# ====================== Routes ======================

@torrent_to_magnet_bp.route('/')
def index():
    return render_template('torrent_to_magnet/index.html')

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
        "magnets": magnets,
        "file": os.path.basename(output_file)
    })

@torrent_to_magnet_bp.route('/magnets', methods=['GET'])
def get_magnets():
    torrent_files = glob.glob(os.path.join(INPUT_DIR, '**', '*.torrent'), recursive=True)
    magnets = []
    for t in torrent_files:
        magnet = torrent_to_magnet(t)
        if magnet:
            magnets.append(magnet)
    
    return jsonify({
        "status": "success",
        "count": len(magnets),
        "magnets": magnets
    })

@torrent_to_magnet_bp.route('/rss', methods=['POST'])
def rss():
    data = request.get_json()
    rss_url = data.get('rss_url', '')
    filters = data.get('filters', '')
    result = download_from_rss(rss_url, filters)
    return jsonify(result)

@torrent_to_magnet_bp.route('/download/<filename>')
def download(filename):
    return send_from_directory(OUTPUT_DIR, filename)