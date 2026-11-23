"""Unit tests for the website-ZIP artifact parser/validator/ZIP builder.

These cover the security boundary for untrusted agent output: path
traversal, extension allowlist, size limits and honest error codes.
"""

import io
import zipfile

from app.services.workflow_files import (
    ArtifactLimits,
    ParsedFile,
    build_zip,
    ensure_project_entry,
    extract_files,
    normalize_path,
    slugify,
)

LIMITS = ArtifactLimits(max_files=50, max_file_bytes=262_144, max_total_bytes=2_097_152)


def block(path, content):
    return f"```file:{path}\n{content}\n```"


def test_extracts_valid_blocks_sorted_and_ignores_prose():
    text = (
        "Here is your website!\n"
        + block("styles.css", "body { margin: 0; }")
        + "\nSome prose between blocks.\n"
        + block("index.html", "<html><body>Hi</body></html>")
        + block("js/app.js", "console.log('ok');")
    )
    result = extract_files(text, LIMITS)
    assert result.error_code is None
    assert [f.path for f in result.files] == ["index.html", "js/app.js", "styles.css"]
    assert result.files[0].content == "<html><body>Hi</body></html>"
    assert result.total_bytes == sum(f.size_bytes for f in result.files)
    assert result.rejected == []


def test_no_blocks_is_artifact_no_files():
    result = extract_files("The agent answered with plain prose only.", LIMITS)
    assert result.files == []
    assert result.error_code == "artifact_no_files"


def test_missing_index_html_is_reported():
    result = extract_files(block("styles.css", "body {}"), LIMITS)
    assert len(result.files) == 1
    assert result.error_code == "artifact_missing_entry"
    assert result.mode == "static"


def test_jsx_tsx_and_project_config_files_are_accepted():
    text = (
        block("src/App.jsx", "export default function App() { return <h1>Hi</h1>; }")
        + block("src/main.tsx", "import App from './App';")
        + block("vite.config.ts", "export default {};")
        + block("tailwind.config.js", "module.exports = {};")
        + block("postcss.config.js", "module.exports = {};")
        + block("tsconfig.json", "{}")
        + block("index.html", "<html></html>")
    )
    result = extract_files(text, LIMITS)
    assert result.rejected == []
    assert {f.path for f in result.files} >= {"src/App.jsx", "src/main.tsx", "vite.config.ts"}


def test_project_mode_needs_no_root_index_html():
    # React/Vite project: package.json + src sources, index.html present is
    # typical but the entry requirement is package.json + a real source.
    text = (
        block("package.json", '{"scripts": {"dev": "vite", "build": "vite build"}}')
        + block("src/App.jsx", "export default function App() { return null; }")
        + block("src/index.css", "@tailwind base;")
    )
    result = extract_files(text, LIMITS)
    assert result.mode == "project"
    assert result.error_code is None


def test_ensure_entry_synthesises_root_index_for_vite_project():
    # The classic failure: the model shipped a CRA-style public/index.html
    # (no module script) and no root index.html — Vite cannot start.
    text = (
        block("package.json", '{"scripts": {"dev": "vite", "build": "vite build"}}')
        + block("public/index.html", "<html><body>%PUBLIC_URL%</body></html>")
        + block("src/main.jsx", "import App from './App';")
        + block("src/App.jsx", "export default function App() { return null; }")
    )
    result = extract_files(text, LIMITS)
    assert result.mode == "project"
    entry = ensure_project_entry(result, "Shop Giày <Dep>")
    assert entry == "index.html"
    created = next(f for f in result.files if f.path == "index.html")
    assert '<div id="root"></div>' in created.content
    assert '<script type="module" src="/src/main.jsx"></script>' in created.content
    assert "Shop Giày &lt;Dep&gt;" in created.content  # title is HTML-escaped


def test_ensure_entry_moves_valid_public_index_to_root():
    public = (
        '<html><body><div id="root"></div>'
        '<script type="module" src="/src/main.jsx"></script></body></html>'
    )
    text = (
        block("package.json", '{"scripts": {"dev": "vite"}}')
        + block("public/index.html", public)
        + block("src/main.jsx", "import App from './App';")
    )
    result = extract_files(text, LIMITS)
    assert ensure_project_entry(result, "Shop") == "index.html"
    paths = [f.path for f in result.files]
    assert "index.html" in paths and "public/index.html" not in paths
    assert next(f for f in result.files if f.path == "index.html").content == public


def test_ensure_entry_noop_when_root_index_exists_or_static():
    text = (
        block("package.json", '{"scripts": {"dev": "vite"}}')
        + block("index.html", "<html><body>root</body></html>")
        + block("src/main.jsx", "import App from './App';")
    )
    result = extract_files(text, LIMITS)
    assert ensure_project_entry(result, "Shop") is None
    static = extract_files(block("styles.css", "body {}"), LIMITS)
    assert ensure_project_entry(static, "Shop") is None


def test_project_mode_bare_package_json_is_not_runnable():
    result = extract_files(block("package.json", "{}"), LIMITS)
    assert result.mode == "project"
    assert result.error_code == "artifact_missing_entry"


def test_project_zip_guide_has_npm_commands_and_honest_build_note():
    files = [
        ParsedFile("package.json", '{"scripts": {"dev": "vite", "build": "vite build"}}'),
        ParsedFile("src/App.jsx", "export default function App() { return null; }"),
    ]
    with zipfile.ZipFile(io.BytesIO(build_zip(files, "Shop", "React landing"))) as archive:
        assert "package.json" in archive.namelist()
        guide = archive.read("HUONG-DAN.md").decode("utf-8")
        assert "npm install" in guide and "npm run dev" in guide and "npm run build" in guide
        assert "chưa được build thử trên server" in guide


def test_path_traversal_and_absolute_paths_are_blocked():
    for bad in ("../evil.html", "a/../../b.html", "/abs.html", "C:\\win.html", ".hidden/x.html"):
        assert normalize_path(bad) is None, bad
    text = block("../evil.html", "x") + block("index.html", "<html></html>")
    result = extract_files(text, LIMITS)
    assert [f.path for f in result.files] == ["index.html"]
    assert any(r["reason"] == "unsafe_path" for r in result.rejected)


def test_executable_and_binary_extensions_are_rejected():
    text = (
        block("run.sh", "rm -rf /")
        + block("app.py", "print(1)")
        + block("setup.bat", "echo hi")
        + block("photo.png", "binary-ish")
        + block("index.html", "<html></html>")
    )
    result = extract_files(text, LIMITS)
    assert [f.path for f in result.files] == ["index.html"]
    rejected = [r for r in result.rejected if r["reason"] == "extension_not_allowed"]
    assert len(rejected) == 4


def test_duplicate_paths_keep_the_first_file():
    text = block("index.html", "first") + block("index.html", "second")
    result = extract_files(text, LIMITS)
    assert len(result.files) == 1 and result.files[0].content == "first"
    assert any(r["reason"] == "duplicate_path" for r in result.rejected)


def test_per_file_size_limit_rejects_oversized_file():
    limits = ArtifactLimits(max_files=50, max_file_bytes=10, max_total_bytes=1_000)
    text = block("index.html", "x" * 50) + block("small.txt", "ok")
    result = extract_files(text, limits)
    assert [f.path for f in result.files] == ["small.txt"]
    assert any(r["reason"] == "file_too_large" for r in result.rejected)


def test_count_and_total_limits_cut_and_report():
    limits = ArtifactLimits(max_files=1, max_file_bytes=1_000, max_total_bytes=1_000)
    text = block("index.html", "<html></html>") + block("extra.css", "body {}")
    result = extract_files(text, limits)
    assert [f.path for f in result.files] == ["index.html"]
    assert result.limit_hit is True
    assert any(r["reason"] == "limit_exceeded" for r in result.rejected)

    tight = ArtifactLimits(max_files=50, max_file_bytes=1_000, max_total_bytes=20)
    text = block("index.html", "x" * 15) + block("b.txt", "y" * 15)
    result = extract_files(text, tight)
    assert [f.path for f in result.files] == ["index.html"]
    assert result.limit_hit is True


def test_build_zip_contains_files_and_system_guide():
    files = [ParsedFile("index.html", "<html>zip</html>"), ParsedFile("styles.css", "body {}")]
    raw = build_zip(files, "My Site", "Build a site")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        assert "index.html" in names and "styles.css" in names
        assert "HUONG-DAN.md" in names
        guide = archive.read("HUONG-DAN.md").decode("utf-8")
        assert "HỆ THỐNG" in guide and "index.html" in guide
        assert archive.read("index.html").decode("utf-8") == "<html>zip</html>"


def test_build_zip_does_not_add_guide_when_agent_shipped_readme():
    files = [ParsedFile("index.html", "<html></html>"), ParsedFile("README.md", "# Mine")]
    with zipfile.ZipFile(io.BytesIO(build_zip(files, "T", "G"))) as archive:
        assert "HUONG-DAN.md" not in archive.namelist()
        assert archive.read("README.md").decode("utf-8") == "# Mine"


def test_slugify_strips_vietnamese_accents():
    assert slugify("Quản lý công việc!") == "quan-ly-cong-viec"
    assert slugify("") == "workflow-website"
    assert slugify("!!!") == "workflow-website"
