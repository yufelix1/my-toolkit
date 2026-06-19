from flask import Flask, render_template
from tools.flatten import flatten_bp
from tools.torrent import torrent_bp

app = Flask(__name__)

app.register_blueprint(flatten_bp, url_prefix='/tools/flatten')
app.register_blueprint(torrent_bp, url_prefix='/tools/torrent')

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)