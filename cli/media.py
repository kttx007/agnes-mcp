import base64, mimetypes, os, sys, urllib.error, urllib.parse, urllib.request

def to_base64(path_or_url, timeout=60):
    """Read local file or download URL, return raw base64 string (no prefix)."""
    if path_or_url.startswith(("http://", "https://")):
        try:
            resp = urllib.request.urlopen(path_or_url, timeout=timeout)
            data = resp.read()
        except urllib.error.HTTPError as e:
            sys.exit(f"Download error {e.code}: {e.read().decode()}")
        except urllib.error.URLError as e:
            sys.exit(f"Download failed: {e}")
    else:
        if not os.path.isfile(path_or_url):
            sys.exit(f"Error: file not found: {path_or_url}")
        with open(path_or_url, "rb") as f:
            data = f.read()
    return base64.b64encode(data).decode()

def upload_to_litterbox(file_path, ttl="1h"):
    if not os.path.isfile(file_path):
        sys.exit(f"Error: file not found: {file_path}")
    boundary = "---- AgnesMediaBoundary"
    filename = os.path.basename(file_path)
    with open(file_path, "rb") as f:
        file_data = f.read()

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="reqtype"\r\n\r\n'
        f"fileupload\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="time"\r\n\r\n'
        f"{ttl}\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="fileToUpload"; filename="{filename}"\r\n'
        f"Content-Type: {mimetypes.guess_type(filename)[0] or 'application/octet-stream'}\r\n\r\n"
    ).encode() + file_data + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        "https://litterbox.catbox.moe/resources/internals/api.php",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
    )
    try:
        url = urllib.request.urlopen(req).read().decode().strip()
    except urllib.error.HTTPError as e:
        sys.exit(f"Upload error {e.code}: {e.read().decode()}")
    except urllib.error.URLError as e:
        sys.exit(f"Upload failed: {e}")
    return url

def resolve(path, ttl="1h"):
    """If local path, upload to Litterbox and return URL. Otherwise return as-is."""
    if path.startswith(("http://", "https://")):
        return path
    return upload_to_litterbox(path, ttl)

def download(url, output_dir="."):
    os.makedirs(output_dir, exist_ok=True)
    name = urllib.parse.urlparse(url).path.split("/")[-1] or "download"
    path = os.path.join(output_dir, name)
    try:
        urllib.request.urlretrieve(url, path)
    except urllib.error.HTTPError as e:
        sys.exit(f"Download error {e.code}: {e.read().decode()}")
    except urllib.error.URLError as e:
        sys.exit(f"Download failed: {e}")
    return path
