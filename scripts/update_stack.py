#!/usr/bin/env python3
import json, os, re, urllib.request, urllib.error
from collections import Counter
from pathlib import Path
from xml.sax.saxutils import escape

USER = os.getenv('PROFILE_USER', 'leon-fabio-weber')
TOKEN = os.getenv('GITHUB_TOKEN', '')
ROOT = Path(__file__).resolve().parents[1]
HEADERS = {'Accept': 'application/vnd.github+json', 'User-Agent': 'profile-stack-generator', 'X-GitHub-Api-Version': '2022-11-28'}
if TOKEN: HEADERS['Authorization'] = f'Bearer {TOKEN}'

def api(path):
    req = urllib.request.Request('https://api.github.com' + path, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=25) as res:
        return json.load(res)

def read_file(repo, path):
    try:
        data = api(f'/repos/{USER}/{repo}/contents/{path}')
        if isinstance(data, dict) and data.get('encoding') == 'base64':
            import base64
            return base64.b64decode(data['content']).decode('utf-8', 'replace')[:120000].lower()
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError):
        pass
    return ''

def collect():
    repos = []
    for page in range(1, 6):
        batch = api(f'/users/{USER}/repos?per_page=100&page={page}&type=owner')
        repos += batch
        if len(batch) < 100: break
    repos = [r for r in repos if not r['fork'] and not r.get('archived') and r['name'] != USER]
    langs = Counter()
    tech = set()
    for r in repos:
        name = r['name']
        try:
            langs.update(api(f'/repos/{USER}/{name}/languages'))
            tree = api(f'/repos/{USER}/{name}/git/trees/{r["default_branch"]}?recursive=1')
            paths = [i['path'] for i in tree.get('tree', []) if i.get('type') == 'blob']
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError, KeyError) as exc:
            print(f'Skipping partial repository data for {name}: {exc}')
            continue
        low = [p.lower() for p in paths]
        if any(p.endswith(('dockerfile', 'docker-compose.yml', 'docker-compose.yaml', 'compose.yml', 'compose.yaml')) for p in low): tech.add('Docker')
        if any(p.endswith(('.tf', '.tfvars')) for p in low): tech.add('Terraform')
        if any(p.endswith(('ansible.cfg', 'playbook.yml', 'playbook.yaml')) for p in low): tech.add('Ansible')
        if any(p.endswith(('package.json',)) for p in low):
            for p in paths:
                if p.lower().endswith('package.json') and p.count('/') <= 2:
                    contents = read_file(name, p)
                    for pattern, label in [('react', 'React'), ('next', 'Next.js'), ('vue', 'Vue'), ('typescript', 'TypeScript'), ('express', 'Express')]:
                        if re.search(r'"(?:@[^" ]+/)?' + re.escape(pattern) + r'(?:/[^" ]+)?"\s*:', contents): tech.add(label)
                    break
        manifests = [p for p in paths if p.lower().split('/')[-1] in ('requirements.txt', 'pyproject.toml', 'pipfile', 'environment.yml', 'environment.yaml') and p.count('/') <= 2][:4]
        for p in manifests:
            content = read_file(name, p)
            for pattern, label in [('torch', 'PyTorch'), ('transformers', 'Hugging Face Transformers'), ('apache-airflow', 'Apache Airflow'), ('scikit-learn', 'scikit-learn'), ('pandas', 'pandas'), ('sqlalchemy', 'SQLAlchemy'), ('tensorflow', 'TensorFlow'), ('fastapi', 'FastAPI'), ('django', 'Django'), ('flask', 'Flask')]:
                if re.search(r'(?<![\w-])' + re.escape(pattern) + r'(?![\w-])', content): tech.add(label)
        if any(p.endswith(('.sql',)) for p in low): tech.add('SQL')
        if any('mysql' in p for p in low): tech.add('MySQL')
    return langs, sorted(tech, key=str.casefold), len(repos)

def svg(langs, tech, count):
    # Language percentages reflect GitHub Linguist bytes, not developer proficiency.
    total = sum(langs.values())
    ranked = langs.most_common(5)
    others = sum(v for _, v in langs.most_common()[5:])
    if others: ranked.append(('Other', others))
    colors = ['#ff893f', '#e9b476', '#7e9ec6', '#86a9a0', '#9b8db8', '#657181']
    width, height = 940, 260
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Repository languages and detected technologies">',
           '<rect width="940" height="260" rx="12" fill="#0d1117"/>',
           '<rect x="1" y="1" width="938" height="258" rx="11" fill="none" stroke="#29313c"/>',
           '<text x="30" y="37" fill="#f2f4f7" font-family="Arial,Helvetica,sans-serif" font-size="18" font-weight="600">Repository overview</text>',
           f'<text x="910" y="35" fill="#a4adba" text-anchor="end" font-family="monospace" font-size="11">{count} PUBLIC REPOS</text>',
           '<text x="30" y="72" fill="#a4adba" font-family="monospace" font-size="11" letter-spacing="1">LANGUAGES BY CODE SIZE</text>']
    x, y, barwidth = 30, 90, 880
    out.append(f'<rect x="{x}" y="{y}" width="{barwidth}" height="13" rx="5" fill="#29313c"/>')
    offset = 0
    for idx, (name, amount) in enumerate(ranked):
        segment = barwidth * amount / total if total else 0
        if segment > 0:
            out.append(f'<rect x="{x+offset:.2f}" y="{y}" width="{segment:.2f}" height="13" fill="{colors[idx]}"/>')
        offset += segment
    cursor = 30
    for idx, (name, amount) in enumerate(ranked):
        percent = amount / total * 100 if total else 0
        label = f'{name} {percent:.1f}%'
        out += [f'<circle cx="{cursor+5}" cy="127" r="4" fill="{colors[idx]}"/>',
                f'<text x="{cursor+15}" y="131" fill="#d8dee6" font-family="Arial,Helvetica,sans-serif" font-size="12">{escape(label)}</text>']
        cursor += max(105, len(label) * 7.3 + 30)
        if cursor > 865: break
    out.append('<text x="30" y="164" fill="#a4adba" font-family="monospace" font-size="11" letter-spacing="1">DETECTED TECHNOLOGIES</text>')
    if not tech: tech = ['No supported dependency manifests detected']
    xx, yy = 30, 178
    for name in tech[:12]:
        pillwidth = len(name) * 7.1 + 23
        if xx + pillwidth > 910:
            xx, yy = 30, yy + 32
        if yy > 214: break
        out.append(f'<rect x="{xx}" y="{yy}" width="{pillwidth:.1f}" height="25" rx="6" fill="#151b23" stroke="#29313c"/>')
        out.append(f'<text x="{xx+11}" y="{yy+17}" fill="#d8dee6" font-family="Arial,Helvetica,sans-serif" font-size="12">{escape(name)}</text>')
        xx += pillwidth + 8
    out.append('<text x="910" y="247" text-anchor="end" fill="#7e8998" font-family="Arial,Helvetica,sans-serif" font-size="10">Public, non-fork repositories · auto-updated</text>')
    out.append('</svg>')
    return '\n'.join(out) + '\n'

if __name__ == '__main__':
    langs, tech, count = collect()
    output = ROOT / 'assets' / 'repository-stack.svg'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(svg(langs, tech, count), encoding='utf-8')
    print(f'Updated {output}: {count} repos, {len(langs)} languages, {len(tech)} technologies')
