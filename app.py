from flask import Flask, render_template
from config import Config

from tools.file_flatten import file_flatten_bp
from tools.torrent_to_magnet import torrent_to_magnet_bp

app = Flask(__name__, 
            static_folder='static', 
            static_url_path='/static',
            template_folder='templates')

app.config.from_object(Config)

# 注册蓝图
app.register_blueprint(file_flatten_bp, url_prefix='/tools/file-flatten')
app.register_blueprint(torrent_to_magnet_bp, url_prefix='/tools/torrent-to-magnet')

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=app.config['DEBUG'])