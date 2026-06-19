from flask import Flask, render_template
from tools.file_flatten import file_flatten_bp
from tools.torrent_to_magnet import torrent_to_magnet_bp

app = Flask(__name__)

# Register blueprints with descriptive URL prefixes
app.register_blueprint(file_flatten_bp, url_prefix='/tools/file-flatten')
app.register_blueprint(torrent_to_magnet_bp, url_prefix='/tools/torrent-to-magnet')

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)