#!/usr/bin/python3
# naws intranet_bookshelf 8888
# http://localhost:8888/books.py?user=papa&mode=img&th=450
import os, sys, re, struct, subprocess, random, tempfile, zipfile, shutil
import cgi, urllib.parse

# options
qs = cgi.FieldStorage()
path = urllib.parse.unquote_plus(qs['p'].value) if 'p' in qs else 'books'
page = int(qs['page'].value) if 'page' in qs and qs['page'].value.isdigit() else 0
mode = qs['mode'].value if 'mode' in qs else 'text'
raw = int(qs['raw'].value) if 'raw' in qs else 0
thumbnail_height = qs['th'].value if 'th' in qs else '150'

# 404 if no valid user specified
progress_path = None
if 'user' in qs and qs['user'].value.isalpha():
  user = qs['user'].value
  progress_path = 'progress_' + user
if not progress_path or not os.path.isdir(progress_path):
  exit(4)

query = f'user={user}&mode={mode}&th={thumbnail_height}'

def read_progress(path):
  progress = 0
  total = 0
  if os.path.isfile(path):
    with open(path, mode='rb') as f:
      # format is { int progress; int total; } but I use to only store progress so I'm mindfull of that
      progress = struct.unpack("i", f.read(4))[0]
      more = f.read(4)
      if len(more) == 4: total = struct.unpack("i", more)[0]
  return (progress, total, progress/(total-1) if total > 1 else 0)

def gen_index(path):
  print(f"""Content-Type:text/html;charset=utf-8\r\n\r\n
  <!DOCTYPE html>
  <html>
  <head>
  <meta charset="utf-8" />
  <title>{path}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link rel="icon" type="image/svg+xml" href="/icon.svg">""")
  print(f"""
  <style>
  div.polaroid {{ display: inline-block; padding: 2px; border-style: solid; border-width: 1px; margin: 2px; }}
  div.container {{ text-align: center; }}
  img {{
    border-radius: 5%;
    max-height: {thumbnail_height}px;
    min-height: {thumbnail_height}px;
    margin-left: auto;
    margin-right: auto;
    display: block;
  }}
  </style>
  </head><body>
  """)
  # if root index, list the 3 most recent activity that aren't at page 0
  if path == 'books':
    progresses = [(name, os.stat(f'{progress_path}/{name}'), f'{progress_path}/{name}') for name in os.listdir(progress_path)]
    progresses = sorted(progresses, key = lambda x: x[1].st_mtime, reverse = True)
    count = 0
    for p in progresses:
      title = p[0]
      # I only get the title, not the path, when dealing with progress files, so I need to search
      # (this allows organizing books without breaking their progress)
      for root, dirs, files in os.walk(path): 
        for file in files + dirs: 
          if file == title:
            progress, total, percent = read_progress(p[2])
            if progress > 0:
              print(f'<a href="?{query}&page={progress}&p={urllib.parse.quote_plus(root)}/{urllib.parse.quote_plus(title)}">Recent: {title} {percent:.2f}</a><br/>')
              count += 1
              break
        if count == 3: break
      if count == 3: break
  # list content
  for filename in sorted(os.listdir(path)):
    filename_safe = urllib.parse.quote_plus(filename)
    path_safe = urllib.parse.quote_plus(path)
    img = ''
    if mode == 'img':
      img_src = get_first_img_src(path, filename)
      if img_src != '404.jpg': img = f'<img src="{img_src}"/>'
    if filename.endswith('.epub') or filename.endswith('.mobi'):
      if mode == 'img':
        print(f"""<div class="polaroid"><a href="{path}/{filename}">{img}</a>
        <div class="container"><a href="{path}/{filename}">{filename}</a></div></div>""")
      else:
        print(f'<a href="{path}/{filename}">{filename}</a><br/>')
    else:
      # progress
      progress, total, percent = read_progress(f'{progress_path}/{filename}')
      if progress > 0:
        progress = f'<a href="?{query}&page={progress}&p={path_safe}/{filename_safe}">(resume {percent:.2f})</a>'
      else:
        progress = '&nbsp;'
      # thumbnail
      if mode == 'img':
        # final link
        print(f"""<div class="polaroid"><a href="?{query}&p={path_safe}/{filename_safe}">{img}</a>
        <div class="container"><p><a href="?{query}&p={path_safe}/{filename_safe}">{filename.replace("_", " ")}</a></p>
        <p>{progress}</p></div></div>""")
      else:
        print(f'<a href="?{query}&p={path_safe}/{filename_safe}">{filename.replace("_", " ")}</a>&nbsp;{progress}<br/>')
  print("""
  </body>
  </html>
  """)

def gen_page(parts):
  # next_page and total number of pages
  n = 0
  current = -1
  next_page = None
  previous_page = None
  on_next = False
  if len(parts) == 1:
    for filename in sorted(os.listdir(os.path.dirname(parts[0]))):
      if filename.lower().endswith('.jpg') or filename.lower().endswith('.jpeg'):
        if on_next: next_page = f'{os.path.dirname(parts[0])}/{filename}'
        on_next = parts[0].endswith(f'/{filename}')
        if on_next: current = n
        if not on_next and not next_page: previous_page = f'{os.path.dirname(parts[0])}/{filename}'
        n += 1
  else:
    with zipfile.ZipFile(parts[0]) as cbz:
      for name in sorted(cbz.namelist()):
        if name.lower().endswith('.jpg') or name.lower().endswith('.jpeg'):
          if on_next: next_page = name
          on_next = name == parts[1]
          if on_next: current = n
          if not on_next and not next_page: previous_page = name
          n += 1
  # save progress
  title = os.path.split(parts[0] if len(parts) > 1 else os.path.dirname(parts[0]))[1]
  with open(f'{progress_path}/{title}', mode='wb') as f:
    f.write(struct.pack('ii', current, n))
  # spew page
  print(f"""Content-Type:text/html;charset=utf-8\r\n\r\n
  <!DOCTYPE html>
  <html>
  <head>
  <meta charset="utf-8" />
  <title>{current}/{n-1} ({current/(n-1):.2f})</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link rel="icon" type="image/svg+xml" href="/icon.svg">""")
  print("""<style>
  * {
    margin: 0.01vh;
    padding: 0.01vh;
  }
  img { min-width: 100%; max-width: 100%; height: auto; }
  </style>
  </head><body>""")
  # encode
  for i in range(len(parts)):
    parts[i] = urllib.parse.quote_plus(parts[i])
  if next_page: next_page = urllib.parse.quote_plus(next_page)
  if previous_page: previous_page = urllib.parse.quote_plus(previous_page)
  # show current page (with link to next page)
  if len(parts) == 1:
    if not next_page: next_page = 'books'
    print(f'<a href="?{query}&p={next_page}"><img src="{parts[0]}" /></a>')
    if previous_page: print(f'<a href="?{query}&p={previous_page}">back</a>')
  else:
    if not next_page:
      print(f'<a href="?{query}&p=books"><img src="?user={user}&raw=1&p={parts[0]}|{parts[1]}" /></a>')
    else:
      print(f'<a href="?{query}&p={parts[0]}|{next_page}"><img src="?user={user}&raw=1&p={parts[0]}|{parts[1]}" /></a>')
    if previous_page: print(f'<a href="?{query}&p={parts[0]}|{previous_page}">back</a>')
  print("""</body></html>""")

def get_first_img_src(path, filename):
  path = f'{path}/{filename}'
  # folder
  if os.path.isdir(path):
    filenames = sorted(os.listdir(path))
    for filename in filenames:
      if filename.lower().endswith('.jpg') or filename.lower().endswith('.jpeg'):
        return f'?user={user}&raw=2&th={thumbnail_height}&p={urllib.parse.quote_plus(path)}/{urllib.parse.quote_plus(filename)}'
    # if category folder, randomly select an entry
    return get_first_img_src(path, random.choice(filenames))
  # zipped comic
  elif path.endswith('.cbz'):
    with zipfile.ZipFile(path) as cbz:
      for name in sorted(cbz.namelist()):
        if name.lower().endswith('.jpg') or name.lower().endswith('.jpeg'):
          return f'?user={user}&raw=2&th={thumbnail_height}&p={urllib.parse.quote_plus(path)}|{urllib.parse.quote_plus(name)}'
  elif path.endswith('.epub') or path.endswith('.mobi'):
    path = urllib.parse.quote_plus(path)
    return f'?user={user}&p={path}'
  else:
    return "404.jpg"

def handle_file(path):
  # folder (either an extracted book, or a root/category folder)
  if os.path.isdir(path):
    # handle first jpg (or page specified)
    count = 0
    for filename in sorted(os.listdir(path)):
      if filename.lower().endswith('.jpg') or filename.lower().endswith('.jpeg'):
        if count == page: return handle_file(f'{path}/{filename}')
        count += 1
    # show index
    return gen_index(path)
  # zipped comic
  elif path.endswith('.cbz'):
    with zipfile.ZipFile(path) as cbz:
      # handle first jpg (or page specified)
      count = 0
      for name in sorted(cbz.namelist()):
        if name.lower().endswith('.jpg') or name.lower().endswith('.jpeg'):
          if count == page: return handle_file(f'{path}|{name}')
          count += 1
  # comic page (as file or inside a zip) (thumbnails or full size)
  elif path.lower().endswith('.jpg') or path.lower().endswith('.jpeg'):
    parts = path.split('|')
    # render the html page
    if raw == 0:
      return gen_page(parts)
    # render the full size image
    elif raw == 1:
      if len(parts) == 1:
        raise Exception("webserver should serve static files where it can, not this script")
      else:
        with zipfile.ZipFile(parts[0]) as cbz:
          with cbz.open(parts[1]) as f:
            print('Content-Type:image/jpeg\r\n\r\n', end='', flush=True)
            shutil.copyfileobj(f, sys.stdout.buffer)
            return 0
    # generate a thumbnail
    elif raw == 2:
      if len(parts) == 1:
        print('Content-Type:image/jpeg\r\n\r\n', end='', flush=True)
        os.execv('/usr/bin/magick', ['magick', 'convert', parts[0], '-thumbnail', f'x{thumbnail_height}>', '-quality', '75', 'jpeg:-'])
      else:
        with zipfile.ZipFile(parts[0]) as cbz:
          with cbz.open(parts[1]) as f:
            print('Content-Type:image/jpeg\r\n\r\n', end='', flush=True)
            subprocess.run(['magick', 'convert', '-', '-thumbnail', f'x{thumbnail_height}>', '-quality', '75', 'jpeg:-'], check=True, input=f.read())
            return 0
  # epub/mobi thumbnailer
  elif path.endswith('.epub') or path.endswith('.mobi'):
    fd, tmp_path = tempfile.mkstemp(suffix='.png', prefix='tmp')
    os.close(fd)
    completedProc = subprocess.run([f'gnome-{path[-4:]}-thumbnailer', '-s', thumbnail_height, path, tmp_path])
    if completedProc.returncode != 0: raise Exception(f'failed to thumbnail {path}')
    with open(tmp_path, mode='rb') as f:
      print('Content-Type:image/png\r\n\r\n', end='', flush=True)
      shutil.copyfileobj(f, sys.stdout.buffer)
    os.remove(tmp_path)
    return 0

  raise Exception(f'unexpected path: {path}')

handle_file(path)
