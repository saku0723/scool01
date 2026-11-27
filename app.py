import hmac
import io
import os
import uuid
from datetime import datetime, timezone
from flask import Flask, render_template, request, redirect, url_for, abort, send_file
from PIL import Image, ImageOps, UnidentifiedImageError

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 6 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 20_000_000
CATEGORIES = ['勉強', '学校行事', '部活動', '進路相談']
SAMPLE = [{'title':'数学のテスト勉強について','body':'二次関数のおすすめの勉強方法を教えてください！','category':'勉強','created':'サンプル','image':''}]
local_posts = []

def storage():
    connection = os.getenv('AZURE_STORAGE_CONNECTION_STRING')
    if not connection:
        return None, None
    from azure.data.tables import TableServiceClient
    from azure.storage.blob import BlobServiceClient
    table = TableServiceClient.from_connection_string(connection).get_table_client('posts')
    blobs = BlobServiceClient.from_connection_string(connection).get_container_client('images')
    return table, blobs

@app.get('/')
def index():
    table, blobs = storage()
    posts = list(table.query_entities("PartitionKey eq 'school'")) if table is not None else list(local_posts)
    posts.sort(key=lambda p: p['created'], reverse=True)
    return render_template('index.html', posts=posts + SAMPLE, categories=CATEGORIES,
                           cloud=table is not None, code_set=bool(os.getenv('POST_CODE')))

@app.post('/post')
def post():
    code = os.getenv('POST_CODE')
    if not code or not hmac.compare_digest(request.form.get('code','').encode(), code.encode()):
        abort(403, '投稿コードが違うか、未設定です。')
    title = request.form.get('title','').strip()
    body = request.form.get('body','').strip()
    category = request.form.get('category','')
    if not (1 <= len(title) <= 80 and 1 <= len(body) <= 1000 and category in CATEGORIES):
        abort(400, '入力内容を確認してください。')
    table, blobs = storage()
    key = uuid.uuid4().hex
    image_name = ''
    upload = request.files.get('image')
    if upload and upload.filename:
        if blobs is None:
            abort(400, '画像投稿にはBlob Storageの設定が必要です。')
        try:
            with Image.open(upload.stream) as source:
                if source.format not in ('JPEG','PNG','WEBP') or source.width * source.height > 20_000_000:
                    abort(400, 'JPEG・PNG・WebP画像を選んでください。')
                img = ImageOps.exif_transpose(source).convert('RGB')
                img.thumbnail((1600,1600))
                output = io.BytesIO()
                img.save(output, format='JPEG', quality=85)
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
            abort(400, '画像を読み込めませんでした。')
        from azure.storage.blob import ContentSettings
        image_name = key + '.jpg'
        blobs.upload_blob(image_name, output.getvalue(), content_settings=ContentSettings(content_type='image/jpeg'))
    entity = {'PartitionKey':'school','RowKey':key,'title':title,'body':body,'category':category,
              'created':datetime.now(timezone.utc).isoformat(timespec='seconds'),'image':image_name}
    if table is not None:
        try:
            table.create_entity(entity)
        except Exception:
            if image_name:
                blobs.delete_blob(image_name)
            raise
    else:
        local_posts.append(entity)
    return redirect(url_for('index'), code=303)

@app.get('/image/<name>')
def image(name):
    import re
    from azure.core.exceptions import ResourceNotFoundError
    if not re.fullmatch(r'(?:[a-f0-9]{32}|sample)\.jpg', name):
        abort(404)
    _, blobs = storage()
    if blobs is None:
        abort(404)
    try:
        data = blobs.download_blob(name).readall()
    except ResourceNotFoundError:
        abort(404)
    return send_file(io.BytesIO(data), mimetype='image/jpeg', max_age=60)

if __name__ == '__main__':
    app.run()
